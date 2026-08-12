"""Passive transport, audit and redaction hardening assertions."""
from utils.redaction import redact_mapping, redact_text


def test_sensitive_response_has_complete_no_cache_headers(client):
    response = client.get('/api/auth/me')
    assert response.headers['Cache-Control'] == 'no-store, no-cache, must-revalidate'
    assert response.headers['Pragma'] == 'no-cache'
    assert response.headers['Expires'] == '0'


def test_https_guard_is_dormant_by_default(client, app):
    app.config['FORCE_HTTPS'] = False
    app.config['IS_PRODUCTION'] = False
    response = client.post('/api/auth/change-password', json={})
    assert response.status_code == 401


def test_https_guard_blocks_sensitive_http_when_enabled(client, app, monkeypatch):
    monkeypatch.setitem(app.config, 'TESTING', False)
    app.config['FORCE_HTTPS'] = True
    response = client.post('/api/auth/change-password', json={})
    assert response.status_code == 403
    assert response.get_json()['code'] == 1
    assert 'HTTPS' in response.get_json()['message']

    # Non-sensitive APIs retain their existing authentication behaviour.
    assert client.get('/api/auth/me').status_code == 401


def test_https_guard_accepts_forwarded_https(client, app, monkeypatch):
    monkeypatch.setitem(app.config, 'TESTING', False)
    app.config['FORCE_HTTPS'] = True
    response = client.post('/api/auth/change-password', json={},
                           headers={'X-Forwarded-Proto': 'https'})
    assert response.status_code == 401


def test_redaction_handles_nested_and_inline_secrets():
    value = redact_mapping({
        'message': 'failed',
        'api_key': 'plain-key',
        'nested': {'appSecret': 'plain-secret', 'status': 400},
    })
    assert value['api_key'] == '***'
    assert value['nested']['appSecret'] == '***'
    assert value['nested']['status'] == 400

    text = redact_text('request failed password=hello token:abc api_key="xyz"')
    assert 'hello' not in text
    assert 'abc' not in text
    assert 'xyz' not in text


def test_user_model_contains_dormant_security_columns(app):
    from sqlalchemy import inspect
    from models import db

    with app.app_context():
        columns = {column['name'] for column in inspect(db.engine).get_columns('users')}
    assert {
        'mfa_secret_encrypted', 'mfa_enabled', 'mfa_op_secret_encrypted', 'mfa_op_enabled',
        'backup_codes_json', 'auth_version', 'vpn_account', 'op_fail_count',
        'op_locked_until', 'login_fail_count', 'login_locked_until', 'mfa_last_counter',
        'mfa_op_last_counter',
    } <= columns


def test_security_alert_rule_targets_admins():
    from utils.wecom_notify import DEFAULT_RULES, EVENT_LABELS, EVENT_SECURITY

    assert EVENT_LABELS[EVENT_SECURITY] == '安全事件告警'
    assert DEFAULT_RULES[EVENT_SECURITY] == {'roles': ['admin']}


def test_device_password_update_and_legacy_reveal_write_table_audit(admin_client, app):
    from models import AuditLog, Customer, Device, db

    with app.app_context():
        customer = Customer(name='传输安全客户')
        db.session.add(customer)
        db.session.flush()
        device = Device(customer_id=customer.id, device_name='传输安全设备')
        db.session.add(device)
        db.session.commit()
        device_id = device.id
        customer_id = customer.id

    payload = {
        'customer_id': customer_id,
        'device_name': '传输安全设备',
        'password': 'NewSecret123!',
        'is_in_use': True,
    }
    response = admin_client.put(f'/api/devices/{device_id}', json=payload,
                                headers={'X-Real-IP': '203.0.113.8'})
    assert response.status_code == 200

    response = admin_client.post(f'/api/devices/{device_id}/reveal-password',
                                 headers={'X-Real-IP': '203.0.113.9'})
    assert response.status_code == 200

    with app.app_context():
        changed = AuditLog.query.filter_by(action='device:password_change',
                                           target_id=device_id).first()
        revealed = AuditLog.query.filter_by(action='device:reveal', target_id=device_id) \
            .order_by(AuditLog.id.desc()).first()
        assert changed is not None
        assert changed.ip == '203.0.113.8'
        assert revealed is not None
        assert revealed.ip == '203.0.113.9'
