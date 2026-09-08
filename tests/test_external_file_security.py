import io
import time

import pytest

from models import Customer, Device, DeviceConfigBackup, SystemSetting, Ticket, SubmissionVersion, db


@pytest.fixture()
def boundary(app):
    with app.app_context():
        db.session.merge(SystemSetting(key='trusted_networks', value='10.0.0.0/8'))
        db.session.commit()


def test_spoofed_ip_cannot_bypass_boundary(admin_client, boundary):
    response = admin_client.get('/api/devices', environ_overrides={'REMOTE_ADDR': '8.8.8.8'},
                                headers={'X-Real-IP': '127.0.0.1', 'X-Forwarded-For': '10.1.2.3'})
    assert response.status_code == 403


def test_report_requires_mfa_but_templates_do_not(admin_client, app, boundary, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    folder = tmp_path / 'static' / 'uploads' / 'ticket_reports'
    folder.mkdir(parents=True)
    (folder / 'report.pdf').write_bytes(b'%PDF-1.4\n%%EOF')
    with app.app_context():
        ticket = Ticket(number='SEC-001', title='security test')
        db.session.add(ticket)
        db.session.flush()
        version = SubmissionVersion(entity_type='ticket', entity_id=ticket.id, version_no=1,
                                    report_file='uploads/ticket_reports/report.pdf')
        db.session.add(version)
        db.session.commit()
        version_id = version.id
    external = {'X-Real-IP': '8.8.8.8'}
    url = f'/api/tickets/report/{version_id}'
    blocked = admin_client.get(url, headers=external)
    assert blocked.status_code == 403 and 'MFA' in blocked.json['message']
    assert admin_client.get('/exports/download-template/device', headers=external).status_code == 200
    with admin_client.session_transaction() as sess:
        sess['auth_strength'] = 'mfa_totp'
        sess['mfa_verified_at'] = sess['login_at']
    allowed = admin_client.get(url, headers=external)
    assert allowed.status_code == 200
    assert 'no-store' in allowed.headers['Cache-Control']
    assert allowed.headers['X-Content-Type-Options'] == 'nosniff'
    assert admin_client.get('/api/devices', headers=external).status_code == 403
    assert admin_client.post('/api/devices/1/reveal-password', headers=external).status_code == 403
    # Expired MFA sessions cannot download even when their MFA fields remain set.
    with admin_client.session_transaction() as sess:
        sess['last_activity'] = int(time.time()) - 100000
    assert admin_client.get(url, headers=external).status_code == 401


@pytest.mark.parametrize('path', ['/static/uploads/configs/1/secret.cfg',
                                 '/static/vendor/../uploads/configs/1/secret.cfg'])
def test_sensitive_static_paths_never_bypass_controlled_routes(admin_client, path):
    assert admin_client.get(path).status_code == 404


def test_config_upload_routes_reject_web_content_before_saving(admin_client, app, tmp_path):
    with app.app_context():
        customer = Customer(name='Upload security')
        db.session.add(customer)
        db.session.flush()
        device = Device(device_name='security-device', customer_id=customer.id)
        db.session.add(device)
        db.session.commit()
        device_id = device.id
    for path, field in [(f'/api/devices/{device_id}/config-backup', 'config_file'),
                        (f'/api/devices/{device_id}/config-backups/upload-from-inspection', 'file')]:
        for name in ('shell.php', 'shell.cfg'):
            response = admin_client.post(path, data={field: (io.BytesIO(b'<?php invalid ?>'), name)},
                                         content_type='multipart/form-data')
            assert response.status_code == 400
    with app.app_context():
        assert DeviceConfigBackup.query.filter_by(device_id=device_id).count() == 0


def test_external_operation_verification_cannot_be_disabled(app, monkeypatch):
    from flask import session
    from models import User
    from utils.operation_token import require_op_token
    from utils.totp import issue_operation_token
    monkeypatch.setattr('utils.access_control.is_internal_request', lambda: False)
    with app.app_context():
        user = User.query.filter_by(username='admin').first()
        uid, version = user.id, user.auth_version
        token = issue_operation_token(uid, version)
    protected = require_op_token()(lambda: 'protected')
    with app.test_request_context('/'):
        session['_user_id'] = str(uid)
        response, status = protected()
        assert status == 403
        assert response.json['message'] == '需要操作动态码验证'
    with app.test_request_context('/', headers={'X-Operation-Token': token}):
        session['_user_id'] = str(uid)
        assert protected() == 'protected'
