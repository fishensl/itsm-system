"""Two-step login and revocable session assertions."""
import time

import pyotp


def _set_setting(app, key, value):
    from models import SystemSetting, db
    with app.app_context():
        db.session.merge(SystemSetting(key=key, value=str(value)))
        db.session.commit()


def test_mfa_enforcement_is_off_by_default(client):
    response = client.post('/api/auth/login', json={'username': 'op', 'password': 'test123456'})
    assert response.status_code == 200
    assert response.get_json()['data']['user']['username'] == 'op'


def test_bound_mfa_always_requires_two_step_login(client, app):
    from models import User, db
    from utils.crypto import encrypt_password
    secret = pyotp.random_base32()
    with app.app_context():
        user = User.query.filter_by(username='op').first()
        user.mfa_secret_encrypted = encrypt_password(secret)
        user.mfa_enabled = True
        db.session.commit()
    first = client.post('/api/auth/login', json={'username': 'op', 'password': 'test123456'})
    assert first.get_json()['data'] == {'mfa_required': True, 'bind_required': False}
    assert client.get('/api/auth/me').status_code == 401
    second = client.post('/api/auth/mfa/verify', json={'code': pyotp.TOTP(secret).now()})
    assert second.status_code == 200
    assert client.get('/api/auth/me').status_code == 200


def test_enforced_unbound_user_can_bind_from_pending_session(client, app):
    _set_setting(app, 'mfa_enforce', '1')
    first = client.post('/api/auth/login', json={'username': 'viewer', 'password': 'test123456'})
    assert first.get_json()['data']['bind_required'] is True
    setup = client.post('/api/auth/mfa/setup', json={'purpose': 'login'}).get_json()['data']
    confirmed = client.post('/api/auth/mfa/confirm', json={
        'purpose': 'login', 'code': pyotp.TOTP(setup['manual_secret']).now(),
    })
    assert confirmed.status_code == 200
    assert confirmed.get_json()['data']['user']['username'] == 'viewer'
    assert client.get('/api/auth/me').status_code == 200


def test_auth_version_revokes_existing_session(op_client, app):
    from models import User, db
    assert op_client.get('/api/auth/me').status_code == 200
    with app.app_context():
        user = User.query.filter_by(username='op').first()
        user.auth_version = int(user.auth_version or 0) + 1
        db.session.commit()
    assert op_client.get('/api/auth/me').status_code == 401


def test_idle_timeout_and_ip_binding(client, app):
    _set_setting(app, 'session_idle_minutes', '5')
    client.post('/api/auth/login', json={'username': 'op', 'password': 'test123456'},
                headers={'X-Real-IP': '10.0.0.1'})
    with client.session_transaction() as sess:
        sess['last_activity'] = int(time.time()) - 301
    assert client.get('/api/auth/me', headers={'X-Real-IP': '10.0.0.1'}).status_code == 401

    client.post('/api/auth/login', json={'username': 'op', 'password': 'test123456'},
                headers={'X-Real-IP': '10.0.0.1'})
    _set_setting(app, 'session_bind_ip', '1')
    assert client.get('/api/auth/me', headers={'X-Real-IP': '10.0.0.2'}).status_code == 401


def test_login_failures_are_persisted_and_locked(client, app):
    for _ in range(5):
        assert client.post('/api/auth/login', json={
            'username': 'viewer', 'password': 'wrong-password',
        }).status_code == 401
    from models import User
    with app.app_context():
        user = User.query.filter_by(username='viewer').first()
        assert user.login_locked_until is not None
