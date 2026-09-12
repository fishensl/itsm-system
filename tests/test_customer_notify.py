from datetime import datetime
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from models import db, Customer, CustomerNotifyBinding, NotificationDelivery, NotifyChannelConfig, InspectionTask
from services import notification_worker as worker
from utils.notify_channels.wecom import WecomChannel
from services import customer_notify_service as service
from services.base import ServiceError
from utils.crypto import encrypt_password, decrypt_password
from utils.json_fields import dumps_json

URL = 'https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=test-customer-secret'


@pytest.fixture
def customer(app):
    with app.app_context():
        row = Customer(name='通知测试客户')
        db.session.add(row)
        db.session.commit()
        return row.id


def test_binding_encrypted_and_clear(app, customer):
    with app.app_context():
        service.save_binding(customer, URL, True)
        row = CustomerNotifyBinding.query.one()
        assert row.webhook_encrypted != URL
        assert decrypt_password(row.webhook_encrypted) == URL
        assert service.settings(customer)['notify_enabled'] is True
        assert service.settings(customer)['has_wecom_webhook'] is True
        from scripts.rotate_secret_key import _collect_rows
        assert any(item.id == row.id and column == 'webhook_encrypted' for item, column in _collect_rows())
        service.save_binding(customer, '', False)
        assert decrypt_password(row.webhook_encrypted) == URL
        service.clear_binding(customer)
        assert not row.fingerprint and not row.webhook_encrypted and not row.enabled


@pytest.mark.parametrize('url', ['http://localhost/a', 'https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=',
    'https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=a&key=b',
    'https://user@qyapi.weixin.qq.com/cgi-bin/webhook/send?key=a'])
def test_invalid_urls_rejected(app, customer, url):
    with app.app_context(), pytest.raises(ServiceError):
        service.save_binding(customer, url, True)


def test_robot_conflict_both_directions(app, customer):
    with app.app_context():
        db.session.add(NotifyChannelConfig(channel_type='wecom', config_json=dumps_json(
            {'webhook_url_encrypted': encrypt_password(URL)})))
        db.session.commit()
        with pytest.raises(ServiceError, match='内部'):
            service.save_binding(customer, URL, True)
        NotifyChannelConfig.query.delete()
        db.session.commit()
        service.save_binding(customer, URL, True)
        with pytest.raises(ServiceError):
            service.ensure_destination_available(URL)
        other = Customer(name='其他客户')
        db.session.add(other)
        db.session.commit()
        with pytest.raises(ServiceError):
            service.save_binding(other.id, URL, True)


def test_customer_delivery_independent_safe_and_deduplicated(app, customer, monkeypatch):
    sent = Mock()
    monkeypatch.setattr(worker, 'send_robot', sent)
    with app.app_context():
        service.save_binding(customer, URL, True)
        from utils.constants import TASK_REVIEWING
        task = InspectionTask(customer_id=customer, actual_start=datetime(2026, 9, 8, 8, 22),
            actual_end=datetime(2026, 9, 8, 10, 10), title='客户2026年第三季度巡检', remark='审核原因秘密', status=TASK_REVIEWING)
        db.session.add(task); db.session.commit()
        worker.process_one()
        sent.assert_called_once()
        text = str(sent.call_args)
        assert '2026-09-08 10:10' in text
        assert task.title in text
        assert '秘密' not in text and '/app/' not in text
        assert NotificationDelivery.query.one().status == 'accepted'


def test_failure_does_not_leak_or_retry(app, customer, monkeypatch):
    monkeypatch.setattr(worker, 'send_robot', Mock(side_effect=RuntimeError(URL)))
    with app.app_context():
        service.save_binding(customer, URL, True)
        assert service.test_binding(customer)
        worker.process_one()
        row = NotificationDelivery.query.one()
        assert row.status == 'unknown'
        assert URL not in str(row.__dict__)


def test_disabled_no_delivery(app, customer, monkeypatch):
    send = Mock()
    monkeypatch.setattr(worker, 'send_robot', send)
    with app.app_context():
        service.save_binding(customer, URL, False)
        ticket = SimpleNamespace(id=1, customer_id=customer, number='WO-1')
        assert not service.notify_ticket(ticket, 'ticket_new')
        assert NotificationDelivery.query.count() == 0
        send.assert_not_called()


def test_api_permissions_and_safe_response(admin_client, viewer_client, customer):
    path = f'/api/customers/{customer}/notify-webhook'
    assert viewer_client.put(path, json={'wecom_webhook': URL, 'notify_enabled': True}).status_code == 403
    result = admin_client.put(path, json={'wecom_webhook': URL, 'notify_enabled': True})
    assert result.status_code == 200, result.get_json()
    assert 'test-customer-secret' not in result.get_data(as_text=True)
    assert admin_client.delete(path).status_code == 200


def test_external_binding_requires_mfa(admin_client, customer, monkeypatch):
    monkeypatch.setattr('utils.access_control.is_internal_request', lambda: False)
    result = admin_client.put(f'/api/customers/{customer}/notify-webhook', json={'notify_enabled': False})
    assert result.status_code == 403
    assert 'MFA' in result.get_json()['message'] or '动态码' in result.get_json()['message']


def test_external_notify_allowlist_does_not_open_customer_management():
    from utils.access_guard import _external_allowed
    assert _external_allowed('/api/customers/12/notify-webhook', 'DELETE')
    assert _external_allowed('/api/customers/12/notify-webhook/test', 'POST')
    assert not _external_allowed('/api/customers/12', 'DELETE')
    assert not _external_allowed('/api/customers/12/notify-webhook/anything', 'GET')


def test_scope_is_enforced_in_observation_mode(app, customer):
    from models import User
    from werkzeug.exceptions import NotFound
    with app.app_context():
        old = app.config['CUSTOMER_SCOPE_ENFORCE']
        app.config['CUSTOMER_SCOPE_ENFORCE'] = False
        try:
            with pytest.raises(NotFound):
                service.require_notify_customer_access(User.query.filter_by(username='op').one(), customer)
        finally:
            app.config['CUSTOMER_SCOPE_ENFORCE'] = old


def test_redirect_is_rejected(monkeypatch):
    from utils.notify_channels.base import NotifyChannel, ChannelError
    send = Mock(return_value=SimpleNamespace(status_code=302, json=lambda: {}))
    monkeypatch.setattr('requests.request', send)
    with pytest.raises(ChannelError):
        NotifyChannel({}, {})._request_json(URL, {})
    assert send.call_args.kwargs['allow_redirects'] is False


def test_wecom_requires_explicit_ack_and_redacts(monkeypatch):
    from utils.notify_channels.base import ChannelError
    channel = WecomChannel({}, {})
    monkeypatch.setattr(channel, '_webhook_url', lambda: URL)
    monkeypatch.setattr(channel, '_request_json', lambda *args: {})
    with pytest.raises(ChannelError, match='未确认'):
        channel.send_text('', 'test', '')
    monkeypatch.setattr(channel, '_request_json', Mock(side_effect=RuntimeError(URL)))
    with pytest.raises(ChannelError) as exc:
        channel.send_text('', 'test', '')
    assert URL not in str(exc.value)


def test_credentials_required_and_csrf(admin_client, app, customer, monkeypatch):
    monkeypatch.setitem(app.config, 'CREDENTIAL_ENVELOPE_MODE', 'required')
    monkeypatch.setitem(app.config, 'CREDENTIAL_ENVELOPE_PURPOSES', service.PURPOSE)
    path = f'/api/customers/{customer}/notify-webhook'
    result = admin_client.put(path, json={'wecom_webhook': URL, 'notify_enabled': True})
    assert result.status_code == 400
    assert '信封' in result.get_json()['message']
    monkeypatch.setitem(app.config, 'WTF_CSRF_ENABLED', True)
    assert admin_client.delete(path).status_code == 400


def test_returned_task_does_not_emit_customer_end(app, monkeypatch):
    from utils.wecom_notify import notify_task_status_changed
    from utils.constants import TASK_RETURNED, TASK_REVIEWING
    send = Mock()
    monkeypatch.setattr(service, 'notify_task', send)
    monkeypatch.setattr('utils.wecom_notify.wecom_broadcast', lambda *a, **kw: (0, 0))
    with app.app_context():
        task = SimpleNamespace(id=1, status=TASK_REVIEWING, actual_end=datetime(2026, 9, 8, 10, 10))
        notify_task_status_changed(task, TASK_RETURNED)
        send.assert_not_called()
