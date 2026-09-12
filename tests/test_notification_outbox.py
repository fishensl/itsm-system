from datetime import datetime, timedelta
from unittest.mock import Mock
import pytest

from models import (db, Customer, Ticket, InspectionTask, NotificationEvent as Event,
                    NotificationDelivery as Delivery, NotificationAttempt, CustomerNotifyBinding)
from services import customer_notify_service as bindings
from services import notification_worker as worker
from services.notification_outbox import insert_event
from utils import constants as C
from utils.notify_channels.customer_robots import DeliveryError

URL = 'https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=outbox-test'


@pytest.fixture
def setup(app, monkeypatch):
    send = Mock()
    monkeypatch.setattr(worker, 'send_robot', send)
    with app.app_context():
        c = Customer(name='Outbox客户')
        db.session.add(c); db.session.commit()
        bindings.save_binding(c.id, URL, True)
        yield c.id, send


def ticket(cid):
    t = Ticket(customer_id=cid, number='WO-outbox', title='交换机端口故障', description='内部秘密不应外发', status=C.TICKET_PENDING_ASSIGN)
    db.session.add(t)
    return t


def test_event_is_atomic_with_business_rollback(setup):
    cid, send = setup
    ticket(cid)
    db.session.flush()
    assert Event.query.filter_by(event_type='ticket_new').count() == 1
    assert Delivery.query.count() == 1
    db.session.rollback()
    assert Event.query.count() == 0
    send.assert_not_called()


def test_commit_does_not_send_and_worker_acknowledges(setup):
    cid, send = setup
    ticket(cid); db.session.commit()
    send.assert_not_called()
    assert worker.process_one()
    send.assert_called_once()
    assert '内部秘密' not in str(send.call_args)
    assert Delivery.query.one().status == 'accepted'
    assert NotificationAttempt.query.count() == 1


def test_customer_fault_notification_uses_business_subject_and_final_timing(setup):
    from utils.json_fields import parse_json
    cid, _ = setup
    t = ticket(cid)
    t.started_at = datetime(2026, 9, 8, 0, 30)
    t.visit_at = datetime(2026, 9, 7, 0, 30)
    db.session.commit()
    initial = parse_json(Event.query.filter_by(event_type='ticket_new').one().payload_json)
    assert initial['title'] == 'Outbox客户交换机端口故障处置'
    assert '处置结束' not in initial['content']
    assert '累计耗时' not in initial['content']
    t.audit_status = '通过'
    t.audit_at = datetime(2026, 9, 8, 9, 30)
    t.audit_comment = '内部审核意见'
    t.status = C.TICKET_CHECKED
    db.session.commit()
    final = parse_json(Event.query.filter_by(event_type='ticket_completed').one().payload_json)
    assert final['title'] == initial['title']
    assert '任务状态：已完成' in final['content']
    assert '处置结束：2026-09-08 17:30' in final['content']
    assert '累计耗时：' in final['content']
    assert '累计人天：' in final['content']
    assert '内部' not in final['content']


def test_retry_limit_and_unknown_result(setup):
    cid, send = setup
    ticket(cid); db.session.commit()
    send.side_effect = DeliveryError('rate_limited', retryable=True)
    for attempt in range(4):
        row = Delivery.query.one(); row.next_attempt_at = datetime.utcnow() - timedelta(seconds=1)
        CustomerNotifyBinding.query.one().next_send_at = None
        db.session.commit(); worker.process_one()
    assert Delivery.query.one().status == 'failed'
    assert send.call_count == 4


def test_network_unknown_not_automatically_retried(setup):
    cid, send = setup
    ticket(cid); db.session.commit()
    send.side_effect = DeliveryError('read_timeout', unknown=True)
    worker.process_one(); worker.process_one()
    assert Delivery.query.one().status == 'unknown'
    assert send.call_count == 1


def test_worker_crash_marks_unknown(setup):
    cid, send = setup
    ticket(cid); db.session.commit()
    worker.claim_one()
    Delivery.query.one().lease_until = datetime.utcnow() - timedelta(seconds=1)
    db.session.commit(); worker.process_one()
    assert Delivery.query.one().status == 'unknown'
    send.assert_not_called()


def test_unbind_and_customer_change_cancel_pending(setup):
    cid, send = setup
    t = ticket(cid); db.session.commit()
    c2 = Customer(name='另一个客户'); db.session.add(c2); db.session.commit()
    t.customer_id = c2.id; db.session.commit(); worker.process_one()
    assert Delivery.query.one().status == 'cancelled'
    send.assert_not_called()


def test_multiple_groups_and_subscription_filters(setup):
    cid, send = setup
    bindings.save_binding(cid, URL + '-2', True, create=True, subscriptions={'ticket_new': False})
    ticket(cid); db.session.commit()
    assert CustomerNotifyBinding.query.count() == 2
    assert Delivery.query.count() == 1


def test_first_submission_frozen_and_not_repeated(setup):
    cid, send = setup
    t = InspectionTask(customer_id=cid, title='内部任务', status=C.TASK_RUNNING,
                       actual_start=datetime(2026, 9, 8, 8, 22))
    db.session.add(t); db.session.commit()
    end = datetime(2026, 9, 8, 10, 10)
    t.status, t.actual_end = C.TASK_REVIEWING, end
    db.session.commit()
    t.status = C.TASK_RETURNED; db.session.commit()
    t.status = C.TASK_REVIEWING; db.session.commit()
    assert Event.query.filter_by(event_type='inspection_field_completed').count() == 1
    assert t.actual_end == end


def test_quiet_hours_defer_and_public_progress_merge(setup):
    from services.notification_outbox import delivery_time
    now = datetime(2026, 9, 10, 15, 0)  # Beijing 23:00
    assert delivery_time({'quiet_start': 22, 'quiet_end': 8, 'digest_minutes': 0}, now, 'ticket_new') == datetime(2026, 9, 11, 0, 0)


def test_event_dedupe_keeps_one_delivery(setup):
    cid, _ = setup
    for _ in range(2):
        insert_event(db.session.connection(), 'ticket_new', {'title': 't', 'content': ''}, customer_id=cid, key='unique-event')
    db.session.commit()
    assert Event.query.count() == 1 and Delivery.query.count() == 1


def test_customer_internal_event_rejected(setup):
    cid, _ = setup
    with pytest.raises(ValueError):
        insert_event(db.session.connection(), 'security_event', {}, customer_id=cid)


def test_disabled_subscription_cancels_retry(setup):
    cid, _ = setup
    ticket(cid); db.session.commit()
    bindings.clear_binding(cid)
    assert Delivery.query.one().status == 'cancelled'


def test_internal_broadcast_queues_without_network(app, monkeypatch):
    from models import NotifyChannelConfig, User
    from utils.crypto import encrypt_password
    from utils.json_fields import dumps_json
    from utils.wecom_notify import wecom_broadcast
    with app.app_context():
        db.session.add(NotifyChannelConfig(channel_type='wecom', is_enabled=True, config_json=dumps_json({'webhook_url_encrypted': encrypt_password(URL)})))
        db.session.commit()
        uid = User.query.filter_by(username='admin').one().id
        http = Mock(); monkeypatch.setattr('requests.request', http)
        wecom_broadcast('ticket_new', 'internal', 'secret content', target_user_ids=[uid])
        assert Delivery.query.count() == 1
        assert 'secret content' not in Event.query.one().payload_json
        http.assert_not_called()


def test_internal_business_event_is_transactional_and_enriched_once(app):
    from models import NotifyChannelConfig, NotifyRule
    from utils.crypto import encrypt_password, decrypt_password
    from utils.json_fields import dumps_json, parse_json
    from utils.wecom_notify import wecom_broadcast
    with app.app_context():
        db.session.add(NotifyChannelConfig(channel_type='wecom', is_enabled=True, config_json=dumps_json({'webhook_url_encrypted': encrypt_password(URL)})))
        db.session.add(NotifyRule(event_type='ticket_new', is_enabled=True, recipients_json=dumps_json({'roles': ['admin']})))
        db.session.commit()
        t = Ticket(number='WO-internal', title='T', status=C.TICKET_PENDING_ASSIGN)
        db.session.add(t); db.session.flush()
        assert Event.query.filter_by(audience='internal').count() == 1
        db.session.rollback()
        assert Event.query.count() == 0
        t = Ticket(number='WO-internal2', title='T', status=C.TICKET_PENDING_ASSIGN)
        db.session.add(t); db.session.commit()
        wecom_broadcast('ticket_new', '完整标题', '完整正文')
        assert Event.query.filter_by(audience='internal').count() == 1
        payload = parse_json(Event.query.one().payload_json, default={})
        assert '完整正文' in decrypt_password(payload['encrypted'])


def test_internal_account_rotation_does_not_reroute_old_event(app, monkeypatch):
    from models import NotifyChannelConfig, User
    from services.notification_outbox import queue_internal
    with app.app_context():
        user = User.query.filter_by(username='admin').one()
        account = {'feishu': 'old-account'}
        monkeypatch.setattr(User, 'notify_accounts', lambda self: dict(account))
        db.session.add(NotifyChannelConfig(channel_type='feishu', is_enabled=True, config_json='{}'))
        db.session.commit()
        queue_internal('ticket_new', 'internal', 'content', user_ids=[user.id])
        account['feishu'] = 'new-account'
        with pytest.raises(DeliveryError, match='channel_or_account_changed'):
            worker._internal_send(Delivery.query.one(), Event.query.one())


def test_approved_inspection_has_subject_and_frozen_effort(setup):
    from datetime import date
    from utils.json_fields import parse_json
    cid, _ = setup
    t = InspectionTask(customer_id=cid, title='景德镇市水利局2026年第3季度巡检',
        status=C.TASK_REVIEWING, scheduled_start=date(2026, 9, 7), scheduled_end=date(2026, 9, 11),
        actual_start=datetime(2026, 9, 8, 8, 30), actual_end=datetime(2026, 9, 8, 17, 30),
        remark='内部审核意见不得发给客户')
    db.session.add(t); db.session.commit()
    assert Event.query.filter_by(event_type='inspection_approved').count() == 0
    t.status = C.TASK_DONE; db.session.commit()
    payload = parse_json(Event.query.filter_by(event_type='inspection_approved').one().payload_json)
    assert payload['title'] == t.title
    assert t.title not in payload['content']
    assert '任务状态：已完成' in payload['content']
    assert '报告' not in payload['title']
    assert '计划时间：2026-09-07 至 2026-09-11' in payload['content']
    assert '实施结束：2026-09-08 17:30' in payload['content']
    assert '累计人天：0.94 人天' in payload['content']
    assert '内部审核意见不得' not in payload['content']
    assert '审核通过' not in payload['content']
    assert '验收' not in payload['content']
