"""一次性 ECDH 凭据传输信封回归。"""
from datetime import datetime, timedelta, timezone
import io
import json

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from models import (CredentialEnvelopeChallenge, Device, DeviceExportRequest,
                    ExportFile, User, db)
from utils.credential_envelope import (
    b64url_decode,
    canonical_json,
    decrypt_payload,
    derive_directional_keys,
    encrypt_payload,
    generate_key_pair,
    public_key_from_jwk,
    public_key_to_jwk,
)
from utils.crypto import decrypt_password, encrypt_password
from services.credential_envelope_service import cleanup_credential_envelopes


def _enable_mfa_session(client):
    now = datetime.now(timezone.utc).isoformat(timespec='milliseconds').replace('+00:00', 'Z')
    with client.session_transaction() as session:
        session['auth_version'] = 0
        session['auth_strength'] = 'mfa_totp'
        session['login_at'] = now
        session['mfa_verified_at'] = now
        session['session_nonce'] = 'test-session-nonce-with-enough-randomness'


def _issue(client, purpose, target_id=None, history_id=None):
    private_key = generate_key_pair()
    response = client.post('/api/security/credential-envelope/challenge', json={
        'version': 1,
        'purpose': purpose,
        'target_id': target_id,
        'history_id': history_id,
        'client_public_key': public_key_to_jwk(private_key.public_key()),
    })
    assert response.status_code == 200, response.get_json()
    challenge = response.get_json()['data']
    peer = public_key_from_jwk(challenge['server_public_key'])
    c2s, s2c = derive_directional_keys(
        private_key, peer, b64url_decode(challenge['salt'], expected_length=32),
        challenge['challenge_id'], challenge['context_hash'])
    return challenge, c2s, s2c


def _request_envelope(challenge, key, payload):
    envelope = encrypt_payload(
        key, canonical_json(payload), b64url_decode(challenge['request_aad']))
    envelope['challenge_id'] = challenge['challenge_id']
    return envelope


def _seed_device():
    device = Device(
        device_name='信封测试交换机', username='admin',
        password_encrypted=encrypt_password('old-secret'),
        login_method='SSH', is_in_use=True,
    )
    db.session.add(device)
    db.session.commit()
    return device.id


def test_capability_allows_compatibility_only_for_disabled_purpose(admin_client, app):
    response = admin_client.get(
        '/api/security/credential-envelope/capability',
        query_string={'purpose': 'device.password.update'},
    )
    assert response.status_code == 200
    assert response.get_json()['data'] == {
        'mode': 'off', 'enabled': False, 'required': False,
    }

    app.config.update(
        CREDENTIAL_ENVELOPE_MODE='optional',
        CREDENTIAL_ENVELOPE_PURPOSES='device.password.update',
    )
    response = admin_client.get(
        '/api/security/credential-envelope/capability',
        query_string={'purpose': 'device.password.update'},
    )
    assert response.status_code == 200
    assert response.get_json()['data'] == {
        'mode': 'optional', 'enabled': True, 'required': False,
    }

    response = admin_client.get(
        '/api/security/credential-envelope/capability',
        query_string={'purpose': 'unknown'},
    )
    assert response.status_code == 400


def test_device_password_update_and_reveal_use_one_time_envelopes(admin_client, app):
    app.config.update(
        CREDENTIAL_ENVELOPE_MODE='required',
        CREDENTIAL_ENVELOPE_PURPOSES=(
            'device.password.update,device.password.reveal'),
        ENVELOPE_WRAP_KEY='MDEyMzQ1Njc4OWFiY2RlZjAxMjM0NTY3ODlhYmNkZWY',
    )
    _enable_mfa_session(admin_client)
    with app.app_context():
        device_id = _seed_device()

    challenge, c2s, _ = _issue(
        admin_client, 'device.password.update', target_id=device_id)
    envelope = _request_envelope(challenge, c2s, {'password': 'new-secret'})
    response = admin_client.put(f'/api/devices/{device_id}', json={
        'device_name': '信封测试交换机',
        'login_method': 'SSH',
        'is_in_use': True,
        'credential_envelope': envelope,
    })
    assert response.status_code == 200, response.get_json()
    with app.app_context():
        assert decrypt_password(db.session.get(Device, device_id).password_encrypted) == 'new-secret'
        row = db.session.get(CredentialEnvelopeChallenge, challenge['challenge_id'])
        assert row.status == 'used'
        assert row.server_private_key_wrapped is None

    replay = admin_client.put(f'/api/devices/{device_id}', json={
        'device_name': '信封测试交换机',
        'login_method': 'SSH',
        'is_in_use': True,
        'credential_envelope': envelope,
    })
    assert replay.status_code == 400

    challenge, c2s, s2c = _issue(
        admin_client, 'device.password.reveal', target_id=device_id)
    response = admin_client.post(f'/api/v2/devices/{device_id}/reveal-password', json={
        'credential_envelope': _request_envelope(
            challenge, c2s, {'history_id': None}),
    })
    assert response.status_code == 200, response.get_json()
    data = response.get_json()['data']
    assert 'password' not in data
    response_envelope = data['credential_envelope']
    plaintext = decrypt_payload(
        s2c, response_envelope['iv'], response_envelope['ciphertext'],
        b64url_decode(challenge['response_aad']))
    assert json.loads(plaintext)['password'] == 'new-secret'


def test_required_mode_rejects_raw_password_and_non_mfa_session(admin_client, app):
    app.config.update(
        CREDENTIAL_ENVELOPE_MODE='required',
        CREDENTIAL_ENVELOPE_PURPOSES='device.password.update',
        ENVELOPE_WRAP_KEY='MDEyMzQ1Njc4OWFiY2RlZjAxMjM0NTY3ODlhYmNkZWY',
    )
    with app.app_context():
        device_id = _seed_device()
    raw = admin_client.put(f'/api/devices/{device_id}', json={
        'device_name': '信封测试交换机', 'login_method': 'SSH',
        'is_in_use': True, 'password': 'must-not-pass',
    })
    assert raw.status_code == 400
    assert '传输信封' in raw.get_json()['message']

    private_key = generate_key_pair()
    challenge = admin_client.post('/api/security/credential-envelope/challenge', json={
        'version': 1,
        'purpose': 'device.password.update',
        'target_id': device_id,
        'client_public_key': public_key_to_jwk(private_key.public_key()),
    })
    assert challenge.status_code == 400
    assert 'MFA' in challenge.get_json()['message']


def test_envelope_rejects_ciphertext_tamper_and_cross_target(admin_client, app):
    app.config.update(
        CREDENTIAL_ENVELOPE_MODE='required',
        CREDENTIAL_ENVELOPE_PURPOSES='device.password.update',
        ENVELOPE_WRAP_KEY='MDEyMzQ1Njc4OWFiY2RlZjAxMjM0NTY3ODlhYmNkZWY',
    )
    _enable_mfa_session(admin_client)
    with app.app_context():
        first_id = _seed_device()
        second = Device(device_name='第二台信封设备', is_in_use=True)
        db.session.add(second)
        db.session.commit()
        second_id = second.id

    challenge, c2s, _ = _issue(
        admin_client, 'device.password.update', target_id=first_id)
    envelope = _request_envelope(challenge, c2s, {'password': 'tamper-canary'})
    first = envelope['ciphertext'][0]
    envelope['ciphertext'] = ('A' if first != 'A' else 'B') + envelope['ciphertext'][1:]
    tampered = admin_client.put(f'/api/devices/{first_id}', json={
        'device_name': '信封测试交换机', 'is_in_use': True,
        'credential_envelope': envelope,
    })
    assert tampered.status_code == 400

    challenge, c2s, _ = _issue(
        admin_client, 'device.password.update', target_id=first_id)
    cross_target = admin_client.put(f'/api/devices/{second_id}', json={
        'device_name': '第二台信封设备', 'is_in_use': True,
        'credential_envelope': _request_envelope(
            challenge, c2s, {'password': 'cross-target-canary'}),
    })
    assert cross_target.status_code == 400
    with app.app_context():
        assert not db.session.get(Device, second_id).password_encrypted


def test_encrypted_device_import_consumes_binary_envelope(admin_client, app):
    app.config.update(
        CREDENTIAL_ENVELOPE_MODE='required',
        CREDENTIAL_ENVELOPE_PURPOSES='device.password.import',
        ENVELOPE_WRAP_KEY='MDEyMzQ1Njc4OWFiY2RlZjAxMjM0NTY3ODlhYmNkZWY',
    )
    _enable_mfa_session(admin_client)
    import openpyxl
    workbook = openpyxl.Workbook()
    sheet = workbook.active
    sheet.append(['名称', '登录密码'])
    sheet.append(['加密导入设备', 'import-secret'])
    source = io.BytesIO()
    workbook.save(source)
    plaintext = source.getvalue()

    challenge, c2s, _ = _issue(admin_client, 'device.password.import')
    iv = b'123456789012'
    ciphertext = AESGCM(c2s).encrypt(
        iv, plaintext, b64url_decode(challenge['request_aad']))
    response = admin_client.post('/api/v2/devices/import', data={
        'challenge_id': challenge['challenge_id'],
        'iv': 'MTIzNDU2Nzg5MDEy',
        'encrypted_file': (io.BytesIO(ciphertext), 'devices.envelope'),
        'original_filename': 'devices.xlsx',
        'mode': 'create',
        'dry_run': '1',
        'clear_empty': '0',
        'network_mappings': '{}',
    }, content_type='multipart/form-data')
    assert response.status_code == 200, response.get_json()
    assert response.get_json()['data']['create'] == 1
    with app.app_context():
        row = db.session.get(CredentialEnvelopeChallenge, challenge['challenge_id'])
        assert row.status == 'used'

    raw = admin_client.post('/api/v2/devices/import', data={
        'import_file': (io.BytesIO(plaintext), 'devices.xlsx'),
        'mode': 'create', 'dry_run': '1',
    }, content_type='multipart/form-data')
    assert raw.status_code == 400
    assert '传输信封' in raw.get_json()['message']


def test_password_export_unlock_password_is_only_in_response_envelope(
        admin_client, app, tmp_path):
    app.config.update(
        CREDENTIAL_ENVELOPE_MODE='required',
        CREDENTIAL_ENVELOPE_PURPOSES='device.password.export_unlock',
        ENVELOPE_WRAP_KEY='MDEyMzQ1Njc4OWFiY2RlZjAxMjM0NTY3ODlhYmNkZWY',
    )
    _enable_mfa_session(admin_client)
    export_path = tmp_path / 'password-export.zip'
    export_path.write_bytes(b'encrypted-zip-placeholder')
    with app.app_context():
        admin = User.query.filter_by(username='admin').one()
        export_file = ExportFile(
            token='export-token-envelope',
            file_path=str(export_path),
            download_name='设备密码表.xlsx',
            created_by_user_id=admin.id,
            file_password_encrypted=encrypt_password('zip-unlock-secret'),
            expires_at=datetime.utcnow() + timedelta(hours=1),
        )
        db.session.add(export_file)
        db.session.add(DeviceExportRequest(
            user_id=admin.id,
            reason='测试', status='approved',
            file_token='export-token-envelope',
            file_password_encrypted=encrypt_password('zip-unlock-secret'),
        ))
        db.session.commit()

    token = 'export-token-envelope'
    challenge, c2s, s2c = _issue(
        admin_client, 'device.password.export_unlock', target_id=token)
    response = admin_client.post(
        f'/api/v2/devices/export-password-download/{token}/authorize', json={
            'credential_envelope': _request_envelope(challenge, c2s, {'token': token}),
        })
    assert response.status_code == 200, response.get_json()
    data = response.get_json()['data']
    assert 'password' not in data
    response_envelope = data['credential_envelope']
    plaintext = decrypt_payload(
        s2c, response_envelope['iv'], response_envelope['ciphertext'],
        b64url_decode(challenge['response_aad']))
    unlock = json.loads(plaintext)
    assert unlock['password'] == 'zip-unlock-secret'

    download = admin_client.get(
        f'/api/v2/devices/export-password-download/{token}/file/'
        f'{unlock["download_ticket"]}')
    assert download.status_code == 200
    assert download.data == b'encrypted-zip-placeholder'
    assert 'X-Export-Password' not in download.headers


def test_expired_envelope_metadata_cleanup(admin_client, app):
    app.config.update(
        CREDENTIAL_ENVELOPE_MODE='optional',
        CREDENTIAL_ENVELOPE_PURPOSES='device.password.update',
        ENVELOPE_WRAP_KEY='MDEyMzQ1Njc4OWFiY2RlZjAxMjM0NTY3ODlhYmNkZWY',
    )
    _enable_mfa_session(admin_client)
    with app.app_context():
        device_id = _seed_device()
    challenge, _c2s, _s2c = _issue(
        admin_client, 'device.password.update', target_id=device_id)
    now = datetime.utcnow()
    with app.app_context():
        row = db.session.get(CredentialEnvelopeChallenge, challenge['challenge_id'])
        row.status = 'used'
        row.server_private_key_wrapped = None
        row.created_at = now - timedelta(days=9)
        row.expires_at = now - timedelta(days=8)
        db.session.commit()
        result = cleanup_credential_envelopes(now=now, retention_days=7)
        assert result['deleted_challenges'] == 1
        assert db.session.get(CredentialEnvelopeChallenge, challenge['challenge_id']) is None


def test_backup_password_uses_envelope_and_required_rejects_raw(admin_client, app):
    app.config.update(
        CREDENTIAL_ENVELOPE_MODE='required',
        CREDENTIAL_ENVELOPE_PURPOSES=(
            'backup.password.export,backup.password.import'),
        ENVELOPE_WRAP_KEY='MDEyMzQ1Njc4OWFiY2RlZjAxMjM0NTY3ODlhYmNkZWY',
    )
    _enable_mfa_session(admin_client)
    challenge, c2s, _s2c = _issue(admin_client, 'backup.password.export')
    response = admin_client.post('/api/system/backup/export', json={
        'config_only': True,
        'credential_envelope': _request_envelope(
            challenge, c2s, {'password': 'backup-canary-secret'}),
    })
    assert response.status_code == 200, response.get_json()
    assert 'password' not in response.get_json()['data']
    token = response.get_json()['data']['token']
    download = admin_client.get(f'/api/system/backup/export-download/{token}')
    assert download.status_code == 200
    assert 'X-Export-Password' not in download.headers
    download.close()

    raw_export = admin_client.post('/api/system/backup/export', json={
        'config_only': True, 'password': 'must-not-pass',
    })
    assert raw_export.status_code == 400
    raw_import = admin_client.post('/api/system/backup/import', data={
        'confirm': '我确认覆盖',
        'password': 'must-not-pass',
        'backup_file': (io.BytesIO(b'not-a-real-zip'), 'backup.zip'),
    }, content_type='multipart/form-data')
    assert raw_import.status_code == 400
