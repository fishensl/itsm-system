"""Default-off MFA and operation verification flows."""
from urllib.parse import parse_qs, unquote, urlparse

import pyotp


def test_mfa_setup_confirm_and_status(op_client, app):
    setup = op_client.post('/api/auth/mfa/setup', json={'purpose': 'login'})
    assert setup.status_code == 200
    data = setup.get_json()['data']
    assert data['qr_data_uri'].startswith('data:image/png;base64,')
    assert len(data['backup_codes']) == 8
    parsed_uri = urlparse(data['provisioning_uri'])
    assert unquote(parsed_uri.path.lstrip('/')) == 'ITSM · 登录（op）'
    assert 'issuer' not in parse_qs(parsed_uri.query)
    assert data['manual_secret'] not in str(op_client.get('/api/auth/mfa/status').get_json())

    code = pyotp.TOTP(data['manual_secret']).now()
    confirm = op_client.post('/api/auth/mfa/confirm', json={'purpose': 'login', 'code': code})
    assert confirm.status_code == 200
    assert op_client.get('/api/auth/mfa/status').get_json()['data']['login_enabled'] is True

    from models import User
    with app.app_context():
        user = User.query.filter_by(username='op').first()
        assert user.mfa_secret_encrypted
        assert data['manual_secret'] not in user.mfa_secret_encrypted
        assert data['backup_codes'][0] not in user.backup_codes_json


def test_operation_code_token_and_default_off_guard(op_client, app):
    from models import Device, SystemSetting, User, db
    from utils.crypto import encrypt_password

    setup = op_client.post('/api/auth/mfa/setup', json={'purpose': 'operation'}).get_json()['data']
    code = pyotp.TOTP(setup['manual_secret']).now()
    assert op_client.post('/api/auth/mfa/confirm',
                          json={'purpose': 'operation', 'code': code}).status_code == 200

    with app.app_context():
        device = Device(device_name='操作码设备', password_encrypted=encrypt_password('secret'))
        db.session.add(device)
        db.session.commit()
        device_id = device.id

    # 开关关闭时，原流程完全不变。
    assert op_client.post(f'/api/v2/devices/{device_id}/reveal-password').status_code == 200

    with app.app_context():
        db.session.merge(SystemSetting(key='op_code_enforce', value='1'))
        db.session.commit()
    blocked = op_client.post(f'/api/v2/devices/{device_id}/reveal-password')
    assert blocked.status_code == 403
    assert blocked.get_json()['message'] == '需要操作动态码验证'

    with app.app_context():
        user = User.query.filter_by(username='op').first()
        secret = __import__('utils.crypto', fromlist=['decrypt_password']) \
            .decrypt_password(user.mfa_op_secret_encrypted)
    verify = op_client.post('/api/auth/op-verify', json={'code': pyotp.TOTP(secret).now()})
    token = verify.get_json()['data']['token']
    revealed = op_client.post(f'/api/v2/devices/{device_id}/reveal-password',
                              headers={'X-Operation-Token': token})
    assert revealed.status_code == 200


def test_operation_failures_persist_and_lock(op_client, app):
    setup = op_client.post('/api/auth/mfa/setup', json={'purpose': 'operation'}).get_json()['data']
    code = pyotp.TOTP(setup['manual_secret']).now()
    op_client.post('/api/auth/mfa/confirm', json={'purpose': 'operation', 'code': code})
    for _ in range(5):
        response = op_client.post('/api/auth/op-verify', json={'code': '000000'})
        assert response.status_code == 400
    from models import User
    with app.app_context():
        user = User.query.filter_by(username='op').first()
        assert user.op_locked_until is not None


def test_admin_mfa_reset_increments_auth_version(admin_client, app):
    from models import User
    with app.app_context():
        target = User.query.filter_by(username='op').first()
        target.mfa_enabled = True
        target.mfa_secret_encrypted = 'encrypted'
        before = target.auth_version or 0
        target_id = target.id
        __import__('models', fromlist=['db']).db.session.commit()
    response = admin_client.post(f'/api/users/{target_id}/mfa-reset', json={'purpose': 'all'})
    assert response.status_code == 200
    with app.app_context():
        target = User.query.get(target_id)
        assert target.mfa_enabled is False
        assert target.auth_version == before + 1
