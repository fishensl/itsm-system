"""Daily idempotent reminders, escalation, private digests and retention."""
from datetime import datetime, timedelta
from sqlalchemy import select
from models import (db, User, InspectionTask, Inspection, Notification, NotificationEvent as Event,
                    NotificationPreference, NotificationDelivery, CustomerNotifyBinding,
                    SubmissionVersion, Ticket, Customer)
from services.notification_outbox import insert_event, CUSTOMER_EVENTS
from utils.json_fields import parse_json
from utils import constants as C


def _inbox(uid, kind, key, title, content, customer_id=None, entity_type='', entity_id=None):
    eid = insert_event(db.session.connection(), kind, {'title': title, 'content': content},
        key=key, audience='inbox', customer_id=customer_id, entity_type=entity_type, entity_id=entity_id,
        targets=[{'target_key': f'inbox:{uid}', 'user_id': uid, 'channel_type': 'inbox'}], lifetime_hours=24)
    return bool(eid)


def periodic(now=None):
    now = now or datetime.utcnow()
    local = now + timedelta(hours=8)
    from services.notification_policy import current, escalation_users
    policy = current()
    if (local.hour, local.minute) < (policy['hour'], policy['minute']):
        return 0
    day = local.strftime('%Y-%m-%d')
    count = 0
    active = {u.id: u for u in User.query.filter_by(is_active=True).all()}
    prefs = {p.user_id: p for p in NotificationPreference.query.all()}
    admins = [u.id for u in active.values() if u.is_admin]
    tasks = InspectionTask.query.filter(InspectionTask.status.in_([
        C.TASK_PENDING, C.TASK_SCHEDULED, C.TASK_RUNNING, C.TASK_REVIEWING, C.TASK_RETURNED])).all()
    for task in tasks:
        uid = task.assigned_to_user_id
        title = ''
        age = 0
        if task.status == C.TASK_RETURNED:
            title = '巡检退回修改待办'
            record = Inspection.query.filter_by(task_id=task.id).order_by(Inspection.id.desc()).first()
            if record and record.reviewed_at:
                age = (now - record.reviewed_at).days
        elif task.status == C.TASK_REVIEWING:
            inspection = Inspection.query.filter_by(task_id=task.id, review_status=C.REVIEW_PENDING).order_by(Inspection.id.desc()).first()
            uid = inspection.reviewer_id if inspection else None
            latest = SubmissionVersion.query.filter_by(entity_type='inspection', entity_id=inspection.id).order_by(SubmissionVersion.version_no.desc()).first() if inspection else None
            if latest and latest.created_at:
                age = (now - latest.created_at).days
            title = '巡检审核超时待办' if age >= policy['review_days'] else ''
        elif task.scheduled_end and task.scheduled_end < local.date() and not task.actual_end:
            age = (local.date() - task.scheduled_end).days
            title = '巡检任务已逾期'
        if not title or uid not in active or (uid in prefs and not prefs[uid].reminders):
            continue
        count += _inbox(uid, 'reminder_task', f'{day}:task:{task.id}:{task.status}:{uid}', title,
            f'任务 #{task.id}，请在任务安排中处理。', task.customer_id, 'task', task.id)
        if age >= policy['escalation_days']:
            for aid in escalation_users(active[uid], active, policy):
                if aid != uid:
                    count += _inbox(aid, 'reminder_escalation', f'{day}:escalate:{task.id}:{aid}',
                        '任务提醒升级', f'任务 #{task.id} 已等待 {age} 天，请协调当前负责人。', task.customer_id, 'task', task.id)
    # Personalized summaries use each user's already-scoped inbox, not global business queries.
    for ticket in Ticket.query.filter(Ticket.status.in_([C.TICKET_SUBMITTED, C.TICKET_PROCESSING, C.TICKET_ASSIGNED, C.TICKET_ACCEPTED])).all():
        assignee = next((u for u in active.values() if ticket.assigned_to in {u.username, u.realname}), None)
        recipients, title, age = [], '', 0
        if ticket.status == C.TICKET_SUBMITTED:
            latest = SubmissionVersion.query.filter_by(entity_type='ticket', entity_id=ticket.id).order_by(SubmissionVersion.version_no.desc()).first()
            if latest and latest.created_at and latest.created_at < now - timedelta(days=policy['review_days']):
                from utils.notifications import review_recipient_ids
                submitter = active.get(latest.submitted_by)
                recipients = review_recipient_ids(submitter.department_id if submitter else None)
                title = '工单审核超时待办'
                age = (now - latest.created_at).days
        elif assignee and (ticket.sla_deadline and ticket.sla_deadline < now):
            recipients, title = [assignee.id], '工单处置已逾期'
            age = (now - ticket.sla_deadline).days
        if assignee and ticket.audit_status == '拒绝' and ticket.status == C.TICKET_PROCESSING:
            recipients, title = [assignee.id], '工单退回修改待办'
            age = (now - ticket.audit_at).days if ticket.audit_at else 0
        for uid in recipients:
            if uid in active and (uid not in prefs or prefs[uid].reminders):
                count += _inbox(uid, 'reminder_ticket', f'{day}:ticket:{ticket.id}:{ticket.status}:{uid}', title,
                    f'工单 {ticket.number}，请查看当前待办。', ticket.customer_id, 'ticket', ticket.id)
                if age >= policy['escalation_days']:
                    for aid in escalation_users(active[uid], active, policy):
                        count += _inbox(aid, 'reminder_escalation', f'{day}:ticket-escalate:{ticket.id}:{aid}',
                            '工单提醒升级', f'工单 {ticket.number} 已等待 {age} 天，请协调当前负责人。', ticket.customer_id, 'ticket', ticket.id)
    for uid, pref in prefs.items():
        if uid not in active:
            continue
        for period, enabled, days in [('daily', pref.daily_digest, 1), ('weekly', pref.weekly_digest and local.weekday() == 0, 7)]:
            if enabled:
                n = Notification.query.filter(Notification.user_id == uid, Notification.is_read.is_(False),
                    Notification.created_at >= now - timedelta(days=days)).count()
                from utils.customer_scope import _configured_customer_ids
                permitted = _configured_customer_ids(active[uid])
                own = InspectionTask.query.filter_by(assigned_to_user_id=uid)
                reviews = Inspection.query.filter_by(reviewer_id=uid, review_status=C.REVIEW_PENDING)
                if permitted is not None:
                    own = own.filter(InspectionTask.customer_id.in_(permitted))
                    reviews = reviews.filter(Inspection.customer_id.in_(permitted))
                returned = own.filter_by(status=C.TASK_RETURNED).count()
                todo = own.filter(InspectionTask.status.in_([C.TASK_PENDING, C.TASK_SCHEDULED, C.TASK_RUNNING])).count()
                overdue = own.filter(InspectionTask.status.in_([C.TASK_PENDING, C.TASK_SCHEDULED, C.TASK_RUNNING]),
                    InspectionTask.scheduled_end < local.replace(hour=0, minute=0, second=0), InspectionTask.actual_end.is_(None)).count()
                tickets = Ticket.query.filter(Ticket.assigned_to.in_([active[uid].username, active[uid].realname]))
                if permitted is not None:
                    tickets = tickets.filter(Ticket.customer_id.in_(permitted))
                open_tickets = tickets.filter(Ticket.status.in_([C.TICKET_ASSIGNED, C.TICKET_ACCEPTED, C.TICKET_PROCESSING, C.TICKET_SUSPENDED]))
                ticket_overdue = open_tickets.filter(Ticket.sla_deadline < now).count()
                ticket_returned = tickets.filter(Ticket.status == C.TICKET_PROCESSING, Ticket.audit_status == '拒绝').count()
                from services.notification_management import scoped_events
                failures = NotificationDelivery.query.filter(NotificationDelivery.event_id.in_(scoped_events(active[uid]).with_entities(Event.id)),
                    NotificationDelivery.status.in_(['failed', 'unknown'])).count()
                pending_versions = SubmissionVersion.query.filter_by(entity_type='ticket', review_status=C.REVIEW_PENDING).all()
                from utils.notifications import review_recipient_ids
                pending_ticket_ids = set()
                for version in pending_versions:
                    submitter = active.get(version.submitted_by)
                    if uid in review_recipient_ids(submitter.department_id if submitter else None):
                        pending_ticket_ids.add(version.entity_id)
                ticket_reviews = Ticket.query.filter(Ticket.id.in_(pending_ticket_ids), Ticket.status == C.TICKET_SUBMITTED)
                if permitted is not None:
                    ticket_reviews = ticket_reviews.filter(Ticket.customer_id.in_(permitted))
                count += _inbox(uid, 'personal_digest', f'{period}:{day}:{uid}', '我的通知摘要',
                    f'巡检待办 {todo} 项，逾期 {overdue} 项，待审 {reviews.count()} 项，退回修改 {returned} 项；'
                    f'工单待办 {open_tickets.count()} 项，逾期 {ticket_overdue} 项，待审 {ticket_reviews.count()} 项，退回修改 {ticket_returned} 项；'
                    f'通知失败/未知 {failures} 项；最近 {days} 天未读通知 {n} 条。')
    # Explicitly opted-in customer summaries include only confirmed service milestones.
    # 继承：上级群开启"下级共用"且订阅摘要时，下级客户当天成果也计入该群摘要。
    from services.customer_notify_service import resolve_bindings
    connection = db.session.connection()
    digest_bindings = [r for r in CustomerNotifyBinding.query.filter_by(enabled=True).all()
                       if parse_json(r.subscriptions_json, default={}).get('customer_digest') is True]
    if digest_bindings:
        all_cids = [cid for (cid,) in db.session.query(Customer.id).all()]
        served_by_binding = {r.id: [] for r in digest_bindings}
        for cid in all_cids:
            bindings, _inherited = resolve_bindings(connection, cid, 'customer_digest')
            for b in bindings:
                if b['id'] in served_by_binding:
                    served_by_binding[b['id']].append(cid)
        for binding in digest_bindings:
            served = served_by_binding.get(binding.id) or []
            if not served:
                continue
            n = Event.query.filter(Event.customer_id.in_(served), Event.audience == 'customer',
                Event.event_type.in_(['ticket_completed', 'inspection_approved']),
                Event.created_at >= now - timedelta(days=1)).count()
            insert_event(connection, 'customer_digest', {'title': CUSTOMER_EVENTS['customer_digest'],
                'content': f'最近一天已确认 {n} 项服务成果。'},
                key=f'customer-summary:{day}:{binding.customer_id}', customer_id=binding.customer_id)
    # Once-per-day failure alert uses the inbox, independent from failing external channels.
    failed = NotificationDelivery.query.filter(NotificationDelivery.status.in_(['failed', 'unknown'])).count()
    if failed:
        for uid in admins:
            count += _inbox(uid, 'delivery_alert', f'delivery-alert:{day}:{uid}', '通知投递需要处理',
                            f'当前有 {failed} 条失败或结果未确认记录，请查看通知中心。')
        from models import customer_engineers
        from utils.permission import has_permission
        affected = db.session.query(Event.customer_id).join(NotificationDelivery, NotificationDelivery.event_id == Event.id).filter(
            NotificationDelivery.status.in_(['failed', 'unknown']), Event.customer_id.isnot(None)).distinct().all()
        for (cid,) in affected:
            for uid in db.session.scalars(select(customer_engineers.c.engineer_id).where(customer_engineers.c.customer_id == cid)):
                if uid not in admins and uid in active and has_permission('customer:notify', active[uid]):
                    count += _inbox(uid, 'delivery_alert', f'delivery-alert:{day}:{cid}:{uid}', '客户通知需要处理',
                                    f'客户 #{cid} 存在失败或结果未知的通知，请查看投递记录。', cid)
    db.session.commit()
    return count


def cleanup(days=90):
    if days < 30:
        raise ValueError('保留时间至少 30 天')
    cutoff = datetime.utcnow() - timedelta(days=days)
    ids = select(Event.id).where(Event.created_at < cutoff, ~Event.id.in_(
        select(NotificationDelivery.event_id).where(NotificationDelivery.status.in_(['pending', 'retry', 'sending']))))
    from models import NotificationAttempt
    dids = select(NotificationDelivery.id).where(NotificationDelivery.event_id.in_(ids))
    NotificationAttempt.query.filter(NotificationAttempt.delivery_id.in_(dids)).delete(synchronize_session=False)
    NotificationDelivery.query.filter(NotificationDelivery.event_id.in_(ids)).delete(synchronize_session=False)
    n = Event.query.filter(Event.id.in_(ids)).delete(synchronize_session=False)
    db.session.commit()
    return n
