"""Authorization-aware history, retries, public progress and acknowledgements."""
from datetime import datetime, timedelta
from models import (db, NotificationEvent as Event, NotificationDelivery as Delivery,
                    NotificationPreference, NotificationWorkerState, Ticket, InspectionTask)
from services.base import ServiceError, transaction
from services.customer_notify_service import require_notify_customer_access
from services.notification_outbox import (CUSTOMER_EVENTS, insert_event, PENDING, RETRY, FAILED, UNKNOWN)
from services.notification_worker import valid_destination
from utils.json_fields import parse_json
from utils import constants as C


def scoped_events(user):
    from utils.customer_scope import _configured_customer_ids
    ids = _configured_customer_ids(user)
    q = Event.query
    if user.has_role('customer_contact'):
        from models import customer_engineers
        return q.filter(Event.customer_id.in_(db.select(customer_engineers.c.customer_id).where(customer_engineers.c.engineer_id == user.id)))
    if ids is not None:
        q = q.filter(Event.customer_id.in_(ids))
    return q


def history(user, page=1, status='', customer_id=None, event_type='', page_size=50, entity_type='', entity_id=None):
    page_size = max(1, min(page_size, 100))
    q = Delivery.query.join(Event, Delivery.event_id == Event.id).filter(Event.id.in_(scoped_events(user).with_entities(Event.id)))
    if status:
        q = q.filter(Delivery.status == status)
    if customer_id:
        q = q.filter(Event.customer_id == customer_id)
    if event_type:
        q = q.filter(Event.event_type == event_type)
    if entity_type and entity_id:
        q = q.filter(Event.entity_type == entity_type, Event.entity_id == entity_id)
    total = q.count()
    rows = q.add_entity(Event).order_by(Delivery.id.desc()).offset((page - 1) * page_size).limit(page_size).all()
    return {'total': total, 'page': page, 'page_size': page_size, 'items': [delivery_payload(r, event) for r, event in rows]}


def delivery_payload(row, e):
    return dict(id=row.id, event_id=e.id, event=CUSTOMER_EVENTS.get(e.event_type, e.event_type),
        customer_id=e.customer_id, audience=e.audience, channel=row.channel_type, target=row.target_key,
        status=row.status, attempts=row.attempts, error_code=row.error_code,
        created_at=e.created_at.isoformat() + 'Z', next_attempt_at=row.next_attempt_at.isoformat() + 'Z')


def get_delivery(user, delivery_id):
    row = db.session.get(Delivery, delivery_id)
    if not row or not scoped_events(user).filter(Event.id == row.event_id).first():
        from werkzeug.exceptions import NotFound
        raise NotFound()
    return row


@transaction
def retry_delivery(user, delivery_id, acknowledge_unknown=False):
    from models import CustomerNotifyBinding
    row = get_delivery(user, delivery_id)
    row = Delivery.query.filter_by(id=row.id).with_for_update().one()
    if row.status not in {FAILED, UNKNOWN}:
        raise ServiceError('只允许补发失败或结果未知的通知')
    if row.status == UNKNOWN and acknowledge_unknown is not True:
        raise ServiceError('请明确确认可能重复发送')
    e = db.session.get(Event, row.event_id)
    reason = valid_destination(row, e, db.session.get(CustomerNotifyBinding, row.binding_id) if row.binding_id else None)
    if reason:
        raise ServiceError('不能补发：' + reason)
    row.status, row.error_code, row.next_attempt_at = PENDING, '', datetime.utcnow()


def metrics(user):
    from sqlalchemy import func
    rows = (db.session.query(Delivery.status, func.count(Delivery.id)).join(Event, Event.id == Delivery.event_id)
            .filter(Event.id.in_(scoped_events(user).with_entities(Event.id))).group_by(Delivery.status).all())
    oldest = (db.session.query(func.min(Event.created_at)).join(Delivery, Delivery.event_id == Event.id)
              .filter(Event.id.in_(scoped_events(user).with_entities(Event.id)), Delivery.status.in_([PENDING, RETRY])).scalar())
    state = db.session.get(NotificationWorkerState, 'worker')
    counts = dict(rows)
    completed = sum(counts.get(k, 0) for k in ('accepted', 'failed', 'unknown'))
    duration = (func.julianday(Delivery.finished_at) - func.julianday(Event.created_at)) * 86400 if db.engine.dialect.name == 'sqlite' else func.extract('epoch', Delivery.finished_at - Event.created_at)
    base = db.session.query(Delivery).join(Event, Event.id == Delivery.event_id).filter(Event.id.in_(scoped_events(user).with_entities(Event.id)))
    average = base.with_entities(func.avg(duration)).filter(Delivery.status == 'accepted', Delivery.finished_at.isnot(None)).scalar()
    def grouped(column):
        return [dict(key=key, status=status, count=count) for key, status, count in base.with_entities(column, Delivery.status, func.count(Delivery.id)).group_by(column, Delivery.status).all()]
    return {'counts': counts, 'average_delivery_seconds': round(float(average), 2) if average is not None else None,
            'by_channel': grouped(Delivery.channel_type), 'by_customer': grouped(Event.customer_id), 'accepted_rate': round(100 * counts.get('accepted', 0) / completed, 1) if completed else None, 'oldest_pending': oldest.isoformat() + 'Z' if oldest else '',
            'worker_healthy': bool(state and state.heartbeat_at > datetime.utcnow() - timedelta(minutes=3))}


@transaction
def publish_progress(user, entity_type, entity_id, content):
    from utils.permission import has_permission
    if entity_type not in ('ticket', 'task') or not isinstance(content, str) or not 1 <= len(content.strip()) <= 500:
        raise ServiceError('请选择工单或巡检并填写 1–500 字的客户可见进展')
    permission = 'ticket:edit' if entity_type == 'ticket' else 'inspection:edit'
    if not has_permission(permission, user):
        raise ServiceError('无权发布该业务进展')
    obj = db.session.get(Ticket if entity_type == 'ticket' else InspectionTask, entity_id)
    if not obj:
        raise ServiceError('业务对象不存在')
    require_notify_customer_access(user, obj.customer_id)
    kind = 'ticket_progress'  # shared public progress event, entity_type retains actual domain
    return insert_event(db.session.connection(), kind, {'title': '客户可见服务进展', 'content': content.strip()},
                        customer_id=obj.customer_id, entity_type=entity_type, entity_id=obj.id)


def portal_events(user, page=1):
    rows = (scoped_events(user).filter(Event.audience == 'customer', Event.event_type != 'test')
            .order_by(Event.created_at.desc()).offset((page - 1) * 50).limit(50).all())
    return [{'id': e.id, 'customer_id': e.customer_id, **parse_json(e.payload_json, default={}),
             'event': e.event_type, 'created_at': e.created_at.isoformat() + 'Z',
             'confirmed_at': e.confirmed_at.isoformat() + 'Z' if e.confirmed_at else '',
             'feedback': e.feedback} for e in rows]


@transaction
def confirm_event(user, event_id, feedback):
    from utils.permission import get_user_scope
    # A global administrative account must not act as the customer's acknowledgement.
    if get_user_scope(user) == 'all':
        raise ServiceError('请使用明确关联客户、数据范围为本人或部门的客户确认账号')
    e = scoped_events(user).filter(Event.id == event_id, Event.audience == 'customer').with_for_update().first()
    if not e or e.event_type not in {'ticket_completed', 'inspection_approved'}:
        raise ServiceError('该事件不支持客户确认')
    require_notify_customer_access(user, e.customer_id)
    cls = Ticket if e.entity_type == 'ticket' else InspectionTask
    obj = db.session.get(cls, e.entity_id)
    if not obj or obj.customer_id != e.customer_id or obj.status not in {C.TICKET_CHECKED, C.TICKET_CLOSED, C.TASK_DONE}:
        raise ServiceError('业务状态或客户归属已变化，不能确认历史成果')
    if e.created_at < datetime.utcnow() - timedelta(days=30):
        raise ServiceError('该确认已超过 30 天有效期')
    if not isinstance(feedback, str) or len(feedback) > 500:
        raise ServiceError('反馈不得超过 500 字')
    if e.confirmed_at:
        return
    e.confirmed_by, e.confirmed_at, e.feedback = user.id, datetime.utcnow(), feedback


@transaction
def preferences(user, data=None):
    row = db.session.get(NotificationPreference, user.id)
    if not row:
        row = NotificationPreference(user_id=user.id, daily_digest=False, weekly_digest=False, reminders=True)
        db.session.add(row)
    if data is not None:
        if not isinstance(data, dict) or set(data) - {'daily_digest', 'weekly_digest', 'reminders'} or any(type(v) is not bool for v in data.values()):
            raise ServiceError('订阅设置不正确')
        for key, value in data.items():
            setattr(row, key, value)
    return {key: getattr(row, key) for key in ('daily_digest', 'weekly_digest', 'reminders')}
