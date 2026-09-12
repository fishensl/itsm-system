"""Transactional events, audience-specific targets and durable delivery state."""
from datetime import datetime, timedelta
import hashlib
from uuid import uuid4

from sqlalchemy import event, inspect, select
from sqlalchemy.orm import Session, object_session
from models import (db, Ticket, InspectionTask, CustomerNotifyBinding, NotificationEvent,
                    NotificationDelivery, NotifyChannelConfig, User)
from utils.json_fields import parse_json, dumps_json
from utils import constants as C

PENDING, SENDING, ACCEPTED = 'pending', 'sending', 'accepted'
RETRY, FAILED, UNKNOWN, CANCELLED = 'retry', 'failed', 'unknown', 'cancelled'
TERMINAL = {ACCEPTED, FAILED, UNKNOWN, CANCELLED}
CUSTOMER_EVENTS = {
    'ticket_new': '工单已受理', 'ticket_assign': '工单已派单', 'ticket_completed': '工单已完成',
    'ticket_progress': '工单服务进展', 'ticket_rescheduled': '工单到访时间变更',
    'inspection_assign': '巡检已安排', 'inspection_started': '巡检已开始',
    'inspection_field_completed': '巡检现场实施已结束', 'inspection_approved': '巡检已完成',
    'inspection_rescheduled': '巡检时间变更', 'inspection_cancelled': '巡检已取消',
    'customer_digest': '客户服务摘要', 'test': '通知渠道测试',
}


def config_hash(value):
    return hashlib.sha256(value.encode()).hexdigest()


def allowed(binding, kind):
    if kind == 'test':
        return True
    settings = parse_json(binding['subscriptions_json'] or '{}', default={})
    return kind in CUSTOMER_EVENTS and settings.get(kind, kind != 'customer_digest') is not False


def delivery_time(binding, now, kind):
    if kind == 'test':
        return now
    # All customer quiet hours are Beijing hours; DB timestamps remain UTC.
    local = now + timedelta(hours=8)
    start, end = binding['quiet_start'], binding['quiet_end']
    result = now
    if start != end and ((start < end and start <= local.hour < end) or
                         (start > end and (local.hour >= start or local.hour < end))):
        resume = local.replace(hour=end, minute=0, second=0, microsecond=0)
        if resume <= local:
            resume += timedelta(days=1)
        result = resume - timedelta(hours=8)
    if kind == 'ticket_progress' and binding['digest_minutes']:
        step = binding['digest_minutes'] * 60
        epoch = datetime(1970, 1, 1)
        seconds = int((result - epoch).total_seconds())
        result = epoch + timedelta(seconds=(seconds // step + 1) * step)
    return result


def insert_event(connection, kind, payload, *, customer_id=None, entity_type='', entity_id=None,
                 key=None, audience='customer', targets=None, lifetime_hours=72):
    """Core inserts share the caller's transaction; never commit or send HTTP."""
    now = datetime.utcnow()
    key = key or str(uuid4())
    if audience == 'customer' and kind not in CUSTOMER_EVENTS:
        raise ValueError('客户事件不在允许范围')
    from sqlalchemy.dialects.postgresql import insert as pg_insert
    from sqlalchemy.dialects.sqlite import insert as sqlite_insert
    insert = pg_insert if connection.dialect.name == 'postgresql' else sqlite_insert
    event_id = str(uuid4())
    version = 1
    if audience == 'customer':
        from services.notification_templates import render
        payload, version = render(connection, kind, payload)
    result = connection.execute(insert(NotificationEvent.__table__).values(
        id=event_id, dedupe_key=key, event_type=kind, audience=audience, customer_id=customer_id,
        entity_type=entity_type, entity_id=entity_id, payload_json=dumps_json(payload),
        template_version=version, created_at=now, expires_at=now + timedelta(hours=lifetime_hours), feedback=''
    ).on_conflict_do_nothing(index_elements=['dedupe_key']))
    if not result.rowcount:
        return None
    if audience == 'customer':
        bindings = connection.execute(select(CustomerNotifyBinding.__table__).where(
            CustomerNotifyBinding.customer_id == customer_id, CustomerNotifyBinding.enabled.is_(True))).mappings()
        targets = [dict(target_key=f'customer:{b["id"]}', binding_id=b['id'], binding_version=b['version'],
                        channel_type=b['channel_type'], next_attempt_at=delivery_time(b, now, kind))
                   for b in bindings if b['webhook_encrypted'] and allowed(b, kind)]
    for target in targets or []:
        connection.execute(NotificationDelivery.__table__.insert().values(
            event_id=event_id, status=PENDING, attempts=0, error_code='',
            **({'next_attempt_at': now} | target)))
    return event_id


def _changed(target, name):
    return inspect(target).attrs[name].history.has_changes()


def _stamp(value):
    return value.strftime('%Y-%m-%d %H:%M') if value else '未记录'


def _business_event(mapper, connection, obj):
    new = inspect(obj).pending
    kinds = []
    if isinstance(obj, Ticket):
        entity = 'ticket'
        from models import Customer
        customer_name = connection.execute(select(Customer.name).where(Customer.id == obj.customer_id)).scalar() if obj.customer_id else ''
        if new and obj.status != C.TICKET_CONTRACT_REVIEW:
            kinds.append('ticket_new')
        if _changed(obj, 'assigned_to') and obj.assigned_to and obj.status != C.TICKET_CONTRACT_REVIEW:
            kinds.append('ticket_assign')
        if not new and _changed(obj, 'visit_at'):
            kinds.append('ticket_rescheduled')
        if _changed(obj, 'status') and obj.status == C.TICKET_CHECKED:
            kinds.append('ticket_completed')
        from utils.notification_content import ticket_fields
        content = '\n'.join(f'{label}：{value}' for label, value in ticket_fields(obj, customer_name=customer_name) if value)
    else:
        entity = 'task'
        if _changed(obj, 'assigned_to_user_id') and obj.assigned_to_user_id and obj.status != C.TASK_CONTRACT_REVIEW:
            kinds.append('inspection_assign')
        if not new and (_changed(obj, 'scheduled_start') or _changed(obj, 'scheduled_end')):
            kinds.append('inspection_rescheduled')
        if _changed(obj, 'status'):
            kind = {C.TASK_RUNNING: 'inspection_started', C.TASK_DONE: 'inspection_approved',
                    C.TASK_CANCELLED: 'inspection_cancelled'}.get(obj.status)
            if kind:
                kinds.append(kind)
            old = inspect(obj).attrs.status.history.deleted
            if obj.status == C.TASK_REVIEWING and C.TASK_RETURNED not in old:
                kinds.append('inspection_field_completed')
        from utils.notification_content import inspection_fields
        content = '\n'.join(f'{label}：{value}' for label, value in inspection_fields(obj) if value)

    for kind in kinds:
        if obj.customer_id is None:
            continue
        key = f'{entity}:{obj.id}:{kind}' if kind in {'inspection_field_completed', 'ticket_new'} else str(uuid4())
        from utils.notification_content import single_line, ticket_subject
        subject = single_line(obj.title) if entity == 'task' else ticket_subject(obj, customer_name=customer_name)
        if entity == 'task':
            public_status = {C.TASK_REVIEWING: '实施已结束', C.TASK_RETURNED: '实施已结束'}.get(obj.status, obj.status)
            public_content = '\n'.join(f'{label}：{value}' for label, value in inspection_fields(obj, status=public_status) if value)
        else:
            public_content = content
        insert_event(connection, kind, {'title': subject or CUSTOMER_EVENTS[kind], 'content': public_content},
                     customer_id=obj.customer_id, entity_type=entity, entity_id=obj.id, key=key)
    internal_kinds = [k for k in kinds if k in {'ticket_new', 'ticket_assign', 'ticket_completed', 'inspection_assign'}]
    if isinstance(obj, Ticket) and _changed(obj, 'status') and obj.status == C.TICKET_SUBMITTED:
        internal_kinds.append('ticket_review_pending')
    if isinstance(obj, InspectionTask) and _changed(obj, 'status') and not new:
        internal_kinds.append('inspection_status_changed')
    if _changed(obj, 'contract_exception_status') and obj.contract_exception_status:
        internal_kinds.append('contract_review')
    from utils.crypto import encrypt_password
    session = object_session(obj)
    for kind in internal_kinds:
        direct = [obj.assigned_to_user_id] if isinstance(obj, InspectionTask) and obj.assigned_to_user_id else []
        if isinstance(obj, Ticket) and obj.assigned_to:
            uid = connection.execute(select(User.id).where((User.username == obj.assigned_to) | (User.realname == obj.assigned_to))).scalar()
            if uid:
                direct.append(uid)
        if kind == 'contract_review':
            from utils.notifications import review_recipient_ids
            requester_name = obj.contract_exception_by or obj.created_by
            requester = User.query.filter((User.username == requester_name) | (User.realname == requester_name)).first()
            direct = review_recipient_ids(requester.department_id if requester else None)
            if requester:
                direct.append(requester.id)
        targets = internal_targets(kind, direct)
        if targets:
            internal_body = content
            if isinstance(obj, InspectionTask) and obj.status == C.TASK_DONE:
                internal_body = '通知事项：巡检审核通过\n' + internal_body
            if isinstance(obj, Ticket) and kind == 'ticket_completed':
                internal_body = '通知事项：审核通过\n' + internal_body
            if isinstance(obj, Ticket) and obj.audit_comment:
                internal_body += '\n审核意见：' + obj.audit_comment
            if isinstance(obj, InspectionTask) and obj.status == C.TASK_RETURNED:
                from models import Inspection, SubmissionVersion
                records = [i for i in session.dirty if isinstance(i, Inspection) and i.task_id == obj.id]
                if records:
                    internal_body += '\n退回原因：' + (records[0].review_comment or '')
                    versions = [v for v in session.dirty if isinstance(v, SubmissionVersion) and v.entity_type == 'inspection' and v.entity_id == records[0].id]
                    if versions and versions[0].revision_requirements and versions[0].revision_requirements.strip() != (records[0].review_comment or '').strip():
                        internal_body += '\n修改要求：' + versions[0].revision_requirements
            from utils.notification_content import ticket_subject
            payload = {'encrypted': encrypt_password(dumps_json({'title': ticket_subject(obj, customer_name=customer_name) if isinstance(obj, Ticket) else obj.title, 'content': internal_body, 'mode': 'text', 'link': ''}))}
            eid = insert_event(connection, kind, payload, audience='internal', targets=targets,
                               customer_id=obj.customer_id, entity_type=entity, entity_id=obj.id)
            session.info.setdefault('notification_enrichment', []).append((kind, eid))


def _inspection_review_event(mapper, connection, obj):
    if not _changed(obj, 'review_status') or obj.review_status != C.REVIEW_PENDING:
        return
    targets = internal_targets('inspection_review_pending', [obj.reviewer_id] if obj.reviewer_id else [])
    if not targets:
        return
    from utils.crypto import encrypt_password
    from utils.wecom_notify import inspection_review_notification_content, inspection_record_review_notification_content
    task = obj.task_rel
    content = inspection_review_notification_content(task) if task else inspection_record_review_notification_content(obj)
    body = {'title': task.title if task else obj.title, 'content': content, 'mode': 'text', 'link': ''}
    eid = insert_event(connection, 'inspection_review_pending', {'encrypted': encrypt_password(dumps_json(body))},
        audience='internal', targets=targets, customer_id=obj.customer_id, entity_type='inspection', entity_id=obj.id)
    object_session(obj).info.setdefault('notification_enrichment', []).append(('inspection_review_pending', eid))


def _ticket_progress_event(mapper, connection, obj):
    targets = internal_targets('ticket_progress')
    if not targets:
        return
    ticket = connection.execute(select(Ticket.__table__).where(Ticket.id == obj.ticket_id)).mappings().first()
    if not ticket:
        return
    from utils.crypto import encrypt_password
    payload = {'title': f'工单 {ticket["number"]} 处置进展', 'content': obj.content or '', 'mode': 'text', 'link': ''}
    eid = insert_event(connection, 'ticket_progress', {'encrypted': encrypt_password(dumps_json(payload))},
        audience='internal', targets=targets, customer_id=ticket['customer_id'], entity_type='ticket', entity_id=ticket['id'])
    object_session(obj).info.setdefault('notification_enrichment', []).append(('ticket_progress', eid))


def _rollback_pending(session):
    session.info.pop('notification_enrichment', None)


def register_business_events():
    for model in (Ticket, InspectionTask):
        for name in ('after_insert', 'after_update'):
            if not event.contains(model, name, _business_event):
                event.listen(model, name, _business_event)
    from models import Inspection, TicketProgress
    if not event.contains(TicketProgress, 'after_insert', _ticket_progress_event):
        event.listen(TicketProgress, 'after_insert', _ticket_progress_event)
    for name in ('after_insert', 'after_update'):
        if not event.contains(Inspection, name, _inspection_review_event):
            event.listen(Inspection, name, _inspection_review_event)
    if not event.contains(Session, 'after_rollback', _rollback_pending):
        event.listen(Session, 'after_rollback', _rollback_pending)


def internal_targets(kind, user_ids=None):
    from utils.notify_channels import _target_user_ids, channel_class
    ids = _target_user_ids(kind, user_ids)
    users = User.query.filter(User.id.in_(ids), User.is_active.is_(True)).all()
    targets = []
    if users:
        for cfg in NotifyChannelConfig.query.filter_by(is_enabled=True).all():
            cls = channel_class(cfg.channel_type)
            if not cls:
                continue
            base = dict(channel_type=cfg.channel_type, config_fingerprint=config_hash(cfg.config_json or ''))
            if cls.delivery_scope == 'channel':
                targets.append(base | {'target_key': f'global:{cfg.channel_type}'})
            else:
                targets.extend(base | {'target_key': f'{cfg.channel_type}:{u.id}', 'user_id': u.id,
                               'config_fingerprint': config_hash((cfg.config_json or '') + '\0' + u.notify_accounts()[cfg.channel_type])}
                               for u in users if u.notify_accounts().get(cfg.channel_type))
    return targets


def queue_internal(kind, title, content='', link='', user_ids=None, mode='text', file_path=None, commit=True, customer_id=None, entity_type='', entity_id=None, key=None):
    from utils.crypto import encrypt_password
    payload = {'encrypted': encrypt_password(dumps_json({'title': title, 'content': content,
               'link': link, 'mode': mode, 'file_path': file_path}))}
    pending = db.session.info.get('notification_enrichment', [])
    match = next(((k, eid) for k, eid in pending if k == kind), None)
    if match:
        pending.remove(match)
        # Never duplicate the transactional event. Enrich its pending snapshot only.
        row = db.session.get(NotificationEvent, match[1])
        if row and not NotificationDelivery.query.filter(NotificationDelivery.event_id == row.id,
                                                         NotificationDelivery.status != PENDING).first():
            row.payload_json = dumps_json(payload)
            if commit:
                db.session.commit()
        return 0, 0
    targets = internal_targets(kind, user_ids)
    if not targets:
        return 0, 0
    # Internal body is encrypted at rest and is never served from customer endpoints.
    insert_event(db.session.connection(), kind, payload, audience='internal', targets=targets, customer_id=customer_id, entity_type=entity_type, entity_id=entity_id, key=key)
    if commit:
        db.session.commit()
    return len(targets), 0
