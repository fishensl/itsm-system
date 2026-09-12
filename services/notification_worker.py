"""Bounded outbox consumer. Network calls occur after the claim transaction commits."""
from datetime import datetime, timedelta
from uuid import uuid4
import random

from models import (db, NotificationEvent as Event, NotificationDelivery as Delivery,
                    NotificationAttempt as Attempt, CustomerNotifyBinding as Binding,
                    NotificationWorkerState, NotifyChannelConfig, Ticket, InspectionTask, Customer, User)
from services.notification_outbox import (PENDING, SENDING, ACCEPTED, RETRY, FAILED, UNKNOWN,
    CANCELLED, config_hash, allowed, delivery_time)
from utils.json_fields import parse_json
from utils.notify_channels.customer_robots import send_robot, DeliveryError


def valid_destination(delivery, event, binding):
    if event.expires_at <= datetime.utcnow():
        return 'expired'
    if event.customer_id and event.entity_type in {'ticket', 'task', 'inspection'}:
        from models import Inspection
        cls = {'ticket': Ticket, 'task': InspectionTask, 'inspection': Inspection}[event.entity_type]
        obj = db.session.get(cls, event.entity_id)
        if not obj or obj.customer_id != event.customer_id:
            return 'customer_changed'
    if event.audience == 'customer':
        if not binding or binding.customer_id != event.customer_id or not db.session.get(Customer, event.customer_id):
            return 'customer_removed'
        if not binding.enabled or not binding.webhook_encrypted or binding.version != delivery.binding_version:
            return 'binding_changed'
        if not allowed(binding.__dict__, event.event_type):
            return 'subscription_disabled'
        cls = {'ticket': Ticket, 'task': InspectionTask}.get(event.entity_type)
        if cls:
            obj = db.session.get(cls, event.entity_id)
            if not obj or obj.customer_id != event.customer_id:
                return 'customer_changed'
    return ''


def recover_expired_leases(now):
    rows = Delivery.query.filter(Delivery.status == SENDING, Delivery.lease_until < now).with_for_update(skip_locked=True).all()
    for row in rows:
        row.status, row.error_code, row.finished_at = UNKNOWN, 'worker_interrupted', now
        db.session.add(Attempt(delivery_id=row.id, number=row.attempts, result=UNKNOWN, error_code=row.error_code))


def claim_one():
    now = datetime.utcnow()
    recover_expired_leases(now)
    row = (Delivery.query.filter(Delivery.status.in_([PENDING, RETRY]), Delivery.next_attempt_at <= now)
           .order_by(Delivery.next_attempt_at, Delivery.id).with_for_update(skip_locked=True).first())
    if not row:
        db.session.commit()
        return None
    event = db.session.get(Event, row.event_id)
    binding = None
    if row.binding_id:
        binding = Binding.query.filter_by(id=row.binding_id).with_for_update().first()
    reason = valid_destination(row, event, binding)
    if reason:
        row.status, row.error_code, row.finished_at = CANCELLED, reason, now
        db.session.commit()
        return False
    if binding:
        next_time = delivery_time(binding.__dict__, now, 'test' if event.event_type == 'test' else 'dispatch')
        if binding.next_send_at and binding.next_send_at > next_time:
            next_time = binding.next_send_at
        if next_time > now:
            row.next_attempt_at = next_time
            db.session.commit()
            return False
        binding.next_send_at = now + timedelta(seconds=3)
    token = str(uuid4())
    row.status, row.lease_token = SENDING, token
    row.lease_until = now + timedelta(seconds=90)
    row.attempts += 1
    ids = [row.id]
    # Coalesce due customer progress for the same object/destination into one text message.
    if binding and binding.digest_minutes and event.event_type == 'ticket_progress':
        others = (Delivery.query.join(Event, Delivery.event_id == Event.id).filter(
            Delivery.id != row.id, Delivery.binding_id == row.binding_id, Delivery.status == PENDING,
            Delivery.next_attempt_at <= now, Event.event_type == event.event_type,
            Event.entity_type == event.entity_type, Event.entity_id == event.entity_id)
            .with_for_update(skip_locked=True, of=Delivery).limit(4).all())
        for other in others:
            ev = db.session.get(Event, other.event_id)
            if valid_destination(other, ev, binding):
                continue
            other.status, other.lease_token, other.lease_until = SENDING, token, row.lease_until
            other.attempts += 1
            ids.append(other.id)
    db.session.commit()
    return ids, token


def _internal_send(row, event):
    if event.audience == 'inbox':
        from models import Notification
        from utils.customer_scope import _configured_customer_ids
        user = db.session.get(User, row.user_id)
        if not user or not user.is_active:
            raise DeliveryError('recipient_inactive')
        ids = _configured_customer_ids(user)
        if event.customer_id and ids is not None and event.customer_id not in ids:
            raise DeliveryError('recipient_scope_changed')
        if event.event_type == 'reminder_task':
            from utils import constants as C
            from models import Inspection
            task = db.session.get(InspectionTask, event.entity_id)
            if not task or task.status in {C.TASK_DONE, C.TASK_CANCELLED}:
                raise DeliveryError('task_resolved')
            responsible = task.assigned_to_user_id
            if task.status == C.TASK_REVIEWING:
                record = Inspection.query.filter_by(task_id=task.id, review_status=C.REVIEW_PENDING).first()
                responsible = record.reviewer_id if record else None
            if responsible != user.id:
                raise DeliveryError('responsible_changed')
        if event.event_type == 'reminder_ticket':
            from utils import constants as C
            ticket = db.session.get(Ticket, event.entity_id)
            if not ticket or ticket.customer_id != event.customer_id or ticket.status in {C.TICKET_CHECKED, C.TICKET_CLOSED}:
                raise DeliveryError('ticket_resolved')
            if ticket.status != C.TICKET_SUBMITTED and ticket.assigned_to not in {user.username, user.realname}:
                raise DeliveryError('responsible_changed')
        if event.event_type == 'reminder_escalation':
            from utils import constants as C
            from services.notification_policy import current, escalation_users
            obj = db.session.get(Ticket if event.entity_type == 'ticket' else InspectionTask, event.entity_id)
            if not obj or obj.status in {C.TICKET_CHECKED, C.TICKET_CLOSED, C.TASK_DONE, C.TASK_CANCELLED}:
                raise DeliveryError('business_resolved')
            active = {u.id: u for u in User.query.filter_by(is_active=True).all()}
            if event.entity_type == 'ticket':
                responsible = [u for u in active.values() if obj.assigned_to in {u.username, u.realname}]
                if obj.status == C.TICKET_SUBMITTED:
                    from models import SubmissionVersion
                    from utils.notifications import review_recipient_ids
                    latest = SubmissionVersion.query.filter_by(entity_type='ticket', entity_id=obj.id).order_by(SubmissionVersion.version_no.desc()).first()
                    submitter = active.get(latest.submitted_by) if latest else None
                    responsible = [active[i] for i in review_recipient_ids(submitter.department_id if submitter else None) if i in active]
            else:
                uid = obj.assigned_to_user_id
                if obj.status == C.TASK_REVIEWING:
                    from models import Inspection
                    inspection = Inspection.query.filter_by(task_id=obj.id, review_status=C.REVIEW_PENDING).first()
                    uid = inspection.reviewer_id if inspection else None
                responsible = [active[uid]] if uid in active else []
            permitted = set().union(*(escalation_users(u, active, current()) for u in responsible))
            if user.id not in permitted:
                raise DeliveryError('escalation_recipient_changed')
        data = parse_json(event.payload_json, default={})
        link = '/app/notification-center' if event.event_type == 'delivery_alert' else '/app/task-schedule' if event.entity_type == 'task' else f'/app/tickets/{event.entity_id}' if event.entity_type == 'ticket' else '/app/notifications'
        if isinstance(data.get('link'), str) and data['link'].startswith('/app/'):
            link = data['link']
        db.session.add(Notification(user_id=user.id, category='system', title=data['title'], content=data['content'], link=link))
        # Inbox insertion and delivery acknowledgement are committed together by process_one.
        return
    from utils.crypto import decrypt_password
    from utils.notify_channels import channel_class
    cfg = NotifyChannelConfig.query.filter_by(channel_type=row.channel_type, is_enabled=True).first()
    if not cfg:
        raise DeliveryError('channel_changed')
    user = db.session.get(User, row.user_id) if row.user_id else None
    if row.user_id and (not user or not user.is_active):
        raise DeliveryError('recipient_inactive')
    account = user.notify_accounts().get(row.channel_type, '') if user else ''
    if row.user_id and not account:
        raise DeliveryError('recipient_unbound')
    fingerprint = config_hash((cfg.config_json or '') + ('\0' + account if row.user_id else ''))
    if fingerprint != row.config_fingerprint:
        raise DeliveryError('channel_or_account_changed')
    if user and event.customer_id:
        from utils.customer_scope import _configured_customer_ids
        ids = _configured_customer_ids(user)
        if ids is not None and event.customer_id not in ids:
            raise DeliveryError('recipient_scope_changed')
    data = parse_json(decrypt_password(parse_json(event.payload_json, default={})['encrypted']), default={})
    if data.get('mode') == 'file':
        raise DeliveryError('attachment_requires_portal')
    channel = channel_class(row.channel_type)({'channel_type': row.channel_type}, parse_json(cfg.config_json, default={}))
    db.session.commit()
    try:
        if data.get('mode') == 'markdown' and channel.supports('markdown'):
            channel.send_markdown(account, data['title'], data.get('content', ''), data.get('link', ''))
        else:
            channel.send_text(account, data['title'], data.get('content', ''), data.get('link', ''))
    except Exception:
        raise DeliveryError('internal_transport_unknown', unknown=True) from None


def process_one():
    claimed = claim_one()
    if not claimed:
        return claimed is False
    ids, token = claimed
    row = db.session.get(Delivery, ids[0])
    event = db.session.get(Event, row.event_id)
    retry_after = 0
    try:
        if event.audience == 'customer':
            binding = db.session.get(Binding, row.binding_id, populate_existing=True)
            reason = valid_destination(row, event, binding)
            if reason:
                raise DeliveryError(reason)
            from services.customer_notify_service import ensure_destination_available
            from utils.crypto import decrypt_password
            ensure_destination_available(decrypt_password(binding.webhook_encrypted), binding.customer_id,
                                         channel_type=binding.channel_type, binding_id=binding.id)
            payloads = [parse_json(db.session.get(Event, db.session.get(Delivery, i).event_id).payload_json, default={}) for i in ids]
            title = payloads[0]['title']
            content = '\n---\n'.join(p.get('content', '') for p in payloads)
            # Snapshot only needed credential fields; no transaction held during HTTP.
            from types import SimpleNamespace
            destination = SimpleNamespace(channel_type=binding.channel_type, webhook_encrypted=binding.webhook_encrypted,
                                          signing_secret_encrypted=binding.signing_secret_encrypted)
            db.session.commit()
            send_robot(destination, title, content)
        else:
            _internal_send(row, event)
        state, error = ACCEPTED, ''
    except DeliveryError as exc:
        state = UNKNOWN if exc.unknown else RETRY if exc.retryable else FAILED
        error = exc.code
        retry_after = exc.retry_after
    except Exception:
        state, error = UNKNOWN, 'unexpected_result'
        db.session.rollback()
    now = datetime.utcnow()
    for item in Delivery.query.filter(Delivery.id.in_(ids), Delivery.lease_token == token, Delivery.status == SENDING).with_for_update().all():
        final = FAILED if state == RETRY and item.attempts >= 4 else state
        item.status, item.error_code = final, error
        item.lease_token, item.lease_until = None, None
        if final == RETRY:
            item.next_attempt_at = now + timedelta(seconds=max(retry_after, min(900, 30 * 2 ** item.attempts) + random.randint(0, 15)))
        else:
            item.finished_at = now
        db.session.add(Attempt(delivery_id=item.id, number=item.attempts, result=final, error_code=error))
    db.session.commit()
    return True


def run_batch(limit=30):
    state = db.session.get(NotificationWorkerState, 'worker')
    if not state:
        state = NotificationWorkerState(id='worker')
        db.session.add(state)
    state.heartbeat_at = datetime.utcnow()
    db.session.commit()
    done = 0
    for _ in range(limit):
        if not process_one():
            break
        done += 1
    return done
