# -*- coding: utf-8 -*-
"""内外网访问隔离（P3）：外网仅放行工单/故障处置流程，敏感模块一律 403

模拟方式：可信网段配置为 10.0.0.0/8，用 X-Real-IP 头模拟内网/外网 IP。
"""
import pytest

from models import db, SystemSetting, Customer
from utils.access_control import (
    TRUSTED_NETWORKS_KEY, ip_in_networks,
)


@pytest.fixture()
def networks(app):
    """配置可信网段 10.0.0.0/8（外网判定生效）；用例结束清理"""
    with app.app_context():
        row = SystemSetting.query.get(TRUSTED_NETWORKS_KEY)
        if not row:
            row = SystemSetting(key=TRUSTED_NETWORKS_KEY)
            db.session.add(row)
        row.value = '10.0.0.0/8'
        db.session.commit()
    yield
    with app.app_context():
        row = SystemSetting.query.get(TRUSTED_NETWORKS_KEY)
        if row:
            db.session.delete(row)
            db.session.commit()


def _get(c, url, ip):
    return c.get(url, headers={'X-Real-IP': ip})


class TestIpMatching:
    def test_cidr_match(self):
        assert ip_in_networks('10.1.2.3', ['10.0.0.0/8'])
        assert not ip_in_networks('192.168.1.5', ['10.0.0.0/8'])

    def test_exact_ip(self):
        assert ip_in_networks('1.2.3.4', ['1.2.3.4'])
        assert not ip_in_networks('1.2.3.5', ['1.2.3.4'])

    def test_default_private_always_internal(self):
        """回环/私网段兜底：命中默认内部网段即内网"""
        from utils.access_control import _DEFAULT_INTERNAL
        assert ip_in_networks('127.0.0.1', _DEFAULT_INTERNAL)
        assert ip_in_networks('192.168.0.5', _DEFAULT_INTERNAL)
        assert ip_in_networks('172.16.0.5', _DEFAULT_INTERNAL)
        assert not ip_in_networks('8.8.8.8', _DEFAULT_INTERNAL)

    def test_invalid_ip_false(self):
        assert not ip_in_networks('not-an-ip', ['10.0.0.0/8'])


@pytest.mark.usefixtures('networks')
class TestExternalBlocked:
    def test_template_permission_denial_preserves_login(self, viewer_client):
        r = _get(viewer_client, '/exports/download-template/device', '8.8.8.8')
        assert r.status_code == 403
        assert 'Location' not in r.headers
        assert _get(viewer_client, '/api/auth/me', '8.8.8.8').status_code == 200

    def test_customers_blocked(self, admin_client):
        r = _get(admin_client, '/api/customers', '8.8.8.8')
        assert r.status_code == 403
        assert r.get_json()['code'] == 1

    def test_devices_blocked(self, admin_client):
        r = _get(admin_client, '/api/devices', '8.8.8.8')
        assert r.status_code == 403

    def test_users_blocked(self, admin_client):
        r = _get(admin_client, '/api/users', '8.8.8.8')
        assert r.status_code == 403

    def test_system_overview_blocked(self, admin_client):
        """系统管理（含通知渠道配置）为内网管理项"""
        r = _get(admin_client, '/api/system/overview', '8.8.8.8')
        assert r.status_code == 403

    def test_ticket_export_blocked(self, admin_client):
        """外网禁止工单导出（批量数据外泄面）"""
        r = _get(admin_client, '/api/tickets/export', '8.8.8.8')
        assert r.status_code == 403

    def test_ticket_delete_blocked(self, admin_client, app):
        with app.app_context():
            from models import Ticket
            db.session.add(Ticket(number='WO-X-1', title='t', customer_id=None))
            db.session.commit()
            tid = Ticket.query.filter_by(number='WO-X-1').first().id
        r = admin_client.delete(f'/api/tickets/{tid}', headers={'X-Real-IP': '8.8.8.8'})
        assert r.status_code == 403


@pytest.mark.usefixtures('networks')
class TestExternalAllowed:
    def test_template_download_without_mfa_preserves_login(self, op_client):
        with op_client.session_transaction() as sess:
            assert sess['auth_strength'] == 'password'
        r = _get(op_client, '/exports/download-template/device', '8.8.8.8')
        assert r.status_code == 200
        assert 'spreadsheetml' in r.content_type
        assert r.data.startswith(b'PK')
        assert 'Location' not in r.headers
        assert _get(op_client, '/api/auth/me', '8.8.8.8').status_code == 200

    def test_template_still_requires_login(self, client):
        r = _get(client, '/exports/download-template/device', '8.8.8.8')
        assert r.status_code in (302, 401)

    def test_dashboard_matches_internal_without_opening_business_modules(self, admin_client):
        internal = _get(admin_client, '/api/dashboard/overview', '10.1.2.3')
        external = _get(admin_client, '/api/dashboard/overview', '8.8.8.8')
        assert internal.status_code == external.status_code == 200
        assert internal.get_json()['data'] == external.get_json()['data']
        assert _get(admin_client, '/api/devices', '8.8.8.8').status_code == 403
        assert _get(admin_client, '/api/customers', '8.8.8.8').status_code == 403

    def test_dashboard_allowance_is_exact_and_readonly(self):
        from utils.access_guard import _external_allowed
        assert not _external_allowed('/api/dashboard/overview', 'POST')
        assert not _external_allowed('/api/dashboard/overview/export', 'GET')

    def test_ticket_list_allowed(self, admin_client):
        r = _get(admin_client, '/api/tickets', '8.8.8.8')
        assert r.status_code == 200

    def test_notifications_allowed(self, admin_client):
        r = _get(admin_client, '/api/notifications', '8.8.8.8')
        assert r.status_code == 200

    def test_faults_allowed(self, admin_client):
        r = _get(admin_client, '/api/faults', '8.8.8.8')
        assert r.status_code == 200

    def test_app_entry_allowed(self, client, tmp_path, monkeypatch):
        """SPA 入口外网可达（未登录时 302 到 /app/login 或 200）"""
        dist = tmp_path / 'app'
        dist.mkdir()
        (dist / 'index.html').write_text('<div id="app"></div>', encoding='utf-8')
        monkeypatch.setattr('blueprints.vue_api._app_dist_dir', lambda: str(dist))
        r = _get(client, '/app/login', '8.8.8.8')
        assert r.status_code in (200, 301, 302)


class TestUploadedStaticFiles:
    def test_sensitive_static_files_are_not_served_even_when_authenticated(
            self, app, client, admin_client, tmp_path):
        original = app.static_folder
        static_dir = tmp_path / 'static'
        upload_dir = static_dir / 'uploads' / 'reports'
        upload_dir.mkdir(parents=True)
        (upload_dir / 'audit.txt').write_text('protected', encoding='utf-8')
        app.static_folder = str(static_dir)
        try:
            anonymous = client.get('/static/uploads/reports/audit.txt')
            authenticated = admin_client.get('/static/uploads/reports/audit.txt')
        finally:
            app.static_folder = original
        assert anonymous.status_code == 404
        assert authenticated.status_code == 404


def test_access_control_exception_fails_closed_for_sensitive_api(
        admin_client, monkeypatch):
    import utils.access_control as access_control

    def _broken_networks():
        raise RuntimeError('database unavailable')

    monkeypatch.setattr(access_control, 'get_trusted_networks', _broken_networks)
    sensitive = admin_client.get('/api/users')
    assert sensitive.status_code == 403
    assert '临时关闭' in sensitive.get_json()['message']
    # 外网工单处置白名单仍按既有权限工作，不因配置读取异常被整体锁死。
    assert admin_client.get('/api/tickets').status_code == 200


@pytest.mark.usefixtures('networks')
class TestInternalAccess:
    def test_customers_ok_internal(self, admin_client, app):
        with app.app_context():
            db.session.add(Customer(name='内网客户'))
            db.session.commit()
        r = _get(admin_client, '/api/customers', '10.1.2.3')
        assert r.status_code == 200
        assert r.get_json()['data']['total'] >= 1

    def test_sidebar_internal_full(self, admin_client):
        r = _get(admin_client, '/api/auth/sidebar-groups', '10.1.2.3')
        keys = [g['key'] for g in r.get_json()['data']]
        assert 'customer' in keys

    def test_sidebar_external_trimmed(self, admin_client):
        """外网侧栏保留真实工作台入口及工单/故障。"""
        r = _get(admin_client, '/api/auth/sidebar-groups', '8.8.8.8')
        groups = r.get_json()['data']
        keys = [g['key'] for g in groups]
        assert keys == ['workbench', 'ops']
        ops = next(g for g in groups if g['key'] == 'ops')
        urls = [c['url'] for c in ops['children']]
        assert all(('/tickets' in u or '/faults' in u) for u in urls)
        wb = next(g for g in groups if g['key'] == 'workbench')
        internal = _get(admin_client, '/api/auth/sidebar-groups', '10.1.2.3').get_json()['data']
        internal_wb = next(g for g in internal if g['key'] == 'workbench')
        assert wb['single_link']['url'] == internal_wb['single_link']['url']


@pytest.mark.usefixtures('networks')
def test_external_mfa_dashboard_and_template_download_keep_session(client, app):
    import pyotp
    from models import User
    from utils.crypto import encrypt_password

    secret = pyotp.random_base32()
    with app.app_context():
        user = User.query.filter_by(username='op').first()
        user.mfa_enabled = True
        user.mfa_secret_encrypted = encrypt_password(secret)
        db.session.commit()
    headers = {'X-Real-IP': '8.8.8.8'}
    login = client.post('/api/auth/login', json={
        'username': 'op', 'password': 'test123456',
    }, headers=headers)
    assert login.get_json()['data']['mfa_required'] is True
    assert client.get('/api/dashboard/overview', headers=headers).status_code == 401
    verified = client.post('/api/auth/mfa/verify', json={
        'code': pyotp.TOTP(secret).now(),
    }, headers=headers)
    assert verified.status_code == 200
    overview = client.get('/api/dashboard/overview', headers=headers)
    assert overview.status_code == 200
    assert overview.get_json()['data']['metrics']
    download = client.get('/exports/download-template/device', headers=headers)
    assert download.status_code == 200
    assert 'spreadsheetml' in download.content_type
    from io import BytesIO
    from openpyxl import load_workbook
    from utils.import_templates import get_import_template
    workbook = load_workbook(BytesIO(download.data))
    assert [cell.value for cell in workbook.active[1]] == get_import_template('device')['headers']
    assert 'Location' not in download.headers
    assert client.get('/api/auth/me', headers=headers).status_code == 200
    assert client.get('/api/devices', headers=headers).status_code == 403

    # 同一个已通过 MFA 的会话撤销模板权限后，仍然不能下载。
    from models import UserPermission
    with app.app_context():
        user = User.query.filter_by(username='op').first()
        db.session.add(UserPermission(user_id=user.id, permission_code='device:add', grant_type='deny'))
        db.session.commit()
    assert client.get('/exports/download-template/device', headers=headers).status_code == 403


@pytest.mark.usefixtures('networks')
class TestTicketPayloadRedaction:
    def test_external_redacts_customer(self, admin_client, app):
        with app.app_context():
            from models import Ticket
            c = Customer(name='脱敏客户', contact_person='张三', phone='13800000001',
                         office='A栋', office_room='101', map_location='xx,xx')
            db.session.add(c)
            db.session.flush()
            db.session.add(Ticket(number='WO-REDACT-1', title='脱敏工单',
                                  customer_id=c.id, customer_name_text='脱敏客户'))
            db.session.commit()
            cid = c.id
            tid = Ticket.query.filter_by(number='WO-REDACT-1').first().id
        # 外网：customer 最小集，customer_id 置空，设备隐藏
        r = _get(admin_client, f'/api/tickets/{tid}', '8.8.8.8')
        d = r.get_json()['data']
        assert d['customer_id'] is None
        assert d['customer'] == {'name': '脱敏客户', 'office': 'A栋',
                                 'office_room': '101', 'map_location': 'xx,xx'}
        assert d['related_device_id'] is None
        # 内网：customer 字段完整、customer 最小集为 None
        r2 = _get(admin_client, f'/api/tickets/{tid}', '10.1.2.3')
        d2 = r2.get_json()['data']
        assert d2['customer_id'] == cid
        assert d2['customer'] is None
