from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
from unittest.mock import Mock
import pytest

from models import (db, User, Customer, Ticket, NotificationEvent as Event, NotificationDelivery as Delivery,
                    customer_engineers)
from services import notification_management as management, notification_worker as worker
from services.customer_notify_service import save_binding
from services.notification_outbox import insert_event
from services.base import ServiceError
from utils import constants as C
from utils.crypto import encrypt_password
from utils.notify_channels.customer_robots import send_robot, validate_robot, DeliveryError


@pytest.fixture
def data(app):
    with app.app_context():
        c = Customer(name='客户A'); b = Customer(name='客户B')
        db.session.add_all([c, b]); db.session.commit()
        user = User.query.filter_by(username='op').one(); user.scope = 'self'
        db.session.execute(customer_engineers.insert().values(customer_id=c.id, engineer_id=user.id))
        db.session.commit()
        yield c, b, user


def test_ack_is_scoped_idempotent_and_preserves_business_time(data):
    c, b, user = data
    t = Ticket(number='WO-ack', title='内部', customer_id=c.id, status=C.TICKET_CHECKED, completed_at=datetime(2026, 9, 10))
    db.session.add(t); db.session.commit()
    e = Event.query.filter_by(event_type='ticket_completed').one()
    management.confirm_event(user, e.id, '已确认')
    at = e.confirmed_at
    management.confirm_event(user, e.id, '不能覆盖')
    assert e.confirmed_at == at and e.feedback == '已确认'
    assert t.completed_at == datetime(2026, 9, 10)
    t.customer_id = b.id; db.session.commit()
    with pytest.raises(ServiceError):
        management.confirm_event(user, e.id, '')


def test_portal_never_returns_internal_or_other_customer(data):
    c, b, user = data
    insert_event(db.session.connection(), 'ticket_new', {'title': 'A', 'content': 'public'}, customer_id=c.id)
    insert_event(db.session.connection(), 'ticket_new', {'title': 'B', 'content': 'other'}, customer_id=b.id)
    insert_event(db.session.connection(), 'security_event', {'encrypted': 'secret'}, audience='internal', customer_id=c.id)
    db.session.commit()
    items = management.portal_events(user)
    assert len(items) == 1 and items[0]['title'] == 'A'


def test_retry_requires_unknown_ack_and_rechecks_binding(data):
    c, _, user = data
    row = save_binding(c.id, 'https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=retry', True)
    insert_event(db.session.connection(), 'ticket_new', {'title': 'T', 'content': ''}, customer_id=c.id)
    db.session.commit()
    delivery = Delivery.query.one(); delivery.status = 'unknown'; db.session.commit()
    with pytest.raises(ServiceError, match='重复'):
        management.retry_delivery(user, delivery.id)
    management.retry_delivery(user, delivery.id, True)
    assert delivery.status == 'pending'
    delivery.status = 'failed'; row.version += 1; db.session.commit()
    with pytest.raises(ServiceError, match='binding_changed'):
        management.retry_delivery(user, delivery.id, True)


def test_templates_are_versioned_and_cannot_execute(data):
    from services.notification_templates import save
    c, _, _ = data
    with pytest.raises(ServiceError):
        save('ticket_new', '{content.__class__}')
    result = save('ticket_new', '服务更新：{content}')
    eid = insert_event(db.session.connection(), 'ticket_new', {'title': 'T', 'content': '公开'}, customer_id=c.id)
    db.session.commit()
    e = db.session.get(Event, eid)
    assert e.template_version == result['version'] and '服务更新' in e.payload_json
    save('ticket_new', '另一个版本 {content}')
    assert '另一个版本' not in e.payload_json


@pytest.mark.parametrize('channel,url', [
    ('wecom', 'https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=test'),
    ('dingtalk', 'https://oapi.dingtalk.com/robot/send?access_token=test'),
    ('feishu', 'https://open.feishu.cn/open-apis/bot/v2/hook/test-uuid'),
])
def test_robot_payloads_signed_and_no_redirect(channel, url, monkeypatch):
    call = Mock(return_value=SimpleNamespace(status_code=200, json=lambda: {'errcode': 0, 'code': 0}))
    monkeypatch.setattr('requests.post', call)
    binding = SimpleNamespace(channel_type=channel, webhook_encrypted=encrypt_password(url), signing_secret_encrypted=encrypt_password('secret'))
    send_robot(binding, '标题', '内容')
    assert call.call_args.kwargs['allow_redirects'] is False
    if channel == 'dingtalk':
        assert 'timestamp=' in call.call_args.args[0] and 'sign=' in call.call_args.args[0]
    if channel == 'feishu':
        assert call.call_args.kwargs['json']['sign']


@pytest.mark.parametrize('channel,url', [('feishu', 'https://localhost/open-apis/bot/v2/hook/a'),
    ('dingtalk', 'https://oapi.dingtalk.com/robot/send?access_token=a&access_token=b'),
    ('feishu', 'https://open.feishu.cn/open-apis/bot/v2/hook/a?redirect=localhost')])
def test_robot_ssrf_rejected(channel, url):
    with pytest.raises(DeliveryError):
        validate_robot(channel, url)


def test_two_consumers_do_not_claim_same_delivery(app, data):
    c, _, _ = data
    if db.engine.dialect.name != 'postgresql':
        pytest.skip('Production concurrent claim contract requires PostgreSQL')
    save_binding(c.id, 'https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=concurrency', True)
    insert_event(db.session.connection(), 'ticket_new', {'title': 'T', 'content': ''}, customer_id=c.id)
    db.session.commit()
    def claim():
        with app.app_context():
            return worker.claim_one()
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: claim(), range(2)))
    assert sum(isinstance(r, tuple) for r in results) == 1


def test_digest_groups_due_public_updates(data, monkeypatch):
    c, _, _ = data
    save_binding(c.id, 'https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=digest', True, digest_minutes=5)
    t = Ticket(number='WO-digest', title='内部', customer_id=c.id, status=C.TICKET_PENDING_ASSIGN)
    db.session.add(t); db.session.commit()
    Delivery.query.delete(); Event.query.delete(); db.session.commit()
    for i in range(3):
        insert_event(db.session.connection(), 'ticket_progress', {'title': '进展', 'content': str(i)}, customer_id=c.id, entity_type='ticket', entity_id=t.id)
    Delivery.query.update({'next_attempt_at': datetime.utcnow() - timedelta(seconds=1)})
    db.session.commit()
    send = Mock(); monkeypatch.setattr(worker, 'send_robot', send)
    worker.process_one()
    assert send.call_count == 1
    assert Delivery.query.filter_by(status='accepted').count() == 3


def test_daily_jobs_idempotent_and_use_current_recipient(data):
    from services.notification_jobs import periodic
    from models import InspectionTask
    c, _, user = data
    task = InspectionTask(customer_id=c.id, title='退回', status=C.TASK_RETURNED, assigned_to_user_id=user.id)
    db.session.add(task); db.session.commit()
    now = datetime(2026, 9, 12, 2, 0)
    periodic(now); periodic(now)
    assert Event.query.filter_by(event_type='reminder_task').count() == 1


def test_api_routes_require_permissions_and_mfa(admin_client, viewer_client, monkeypatch):
    assert viewer_client.get('/api/notify-center').status_code == 403
    assert viewer_client.get('/api/customer-notifications').status_code == 403
    monkeypatch.setattr('utils.access_control.is_internal_request', lambda: False)
    r = admin_client.post('/api/notify-center/1/retry', json={'acknowledge_unknown': True})
    assert r.status_code == 403 and ('MFA' in r.get_json()['message'] or '动态码' in r.get_json()['message'])


def test_contact_api_cannot_confirm_other_customer(app, op_client, data):
    from models import UserPermission
    c, b, user = data
    db.session.add(UserPermission(user_id=user.id, permission_code='customer:confirm', grant_type='grant'))
    t = Ticket(number='WO-contact', title='内部标题', customer_id=b.id, status=C.TICKET_CHECKED)
    db.session.add(t); db.session.commit()
    e = Event.query.filter_by(customer_id=b.id, event_type='ticket_completed').one()
    response = op_client.post(f'/api/customer-notifications/{e.id}/confirm', json={'feedback': ''})
    assert response.status_code == 400
    assert not e.confirmed_at
    assert op_client.get('/api/customer-notifications').get_json()['data']['items'] == []


def test_cleanup_keeps_active_deliveries(data):
    from services.notification_jobs import cleanup
    c, _, _ = data
    save_binding(c.id, 'https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=cleanup', True)
    eid = insert_event(db.session.connection(), 'ticket_new', {'title': 'T', 'content': ''}, customer_id=c.id)
    db.session.commit()
    e = db.session.get(Event, eid); e.created_at = datetime.utcnow() - timedelta(days=100)
    db.session.commit()
    assert cleanup() == 0
    Delivery.query.one().status = 'accepted'; db.session.commit()
    assert cleanup() == 1


def test_robot_respects_retry_after(monkeypatch):
    monkeypatch.setattr('requests.post', Mock(return_value=SimpleNamespace(status_code=429, headers={'Retry-After': '180'})))
    binding = SimpleNamespace(channel_type='wecom', webhook_encrypted=encrypt_password('https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=wait'), signing_secret_encrypted='')
    with pytest.raises(DeliveryError) as error:
        send_robot(binding, 'test', '')
    assert error.value.retryable and error.value.retry_after == 180


def test_history_filters_object_and_paginates(data):
    c, _, user = data
    save_binding(c.id, 'https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=history', True)
    for entity_id in (1, 1, 2):
        insert_event(db.session.connection(), 'ticket_new', {'title': 'T', 'content': ''}, customer_id=c.id, entity_type='ticket', entity_id=entity_id)
    db.session.commit()
    result = management.history(user, page=2, page_size=1, entity_type='ticket', entity_id=1)
    assert result['total'] == 2 and len(result['items']) == 1 and result['page_size'] == 1
