# -*- coding: utf-8 -*-
"""内外网访问隔离：业务模块按权限开放，敏感读取要求 MFA。

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


def test_version_asset_does_not_disclose_configuration():
    from types import SimpleNamespace
    from services.submission_version_service import _asset_payload
    asset = SimpleNamespace(id=1, asset_type='config_text', file_path='', file_name='a.cfg',
                            device_id=None, content_text='secret-config', target_id=None,
                            skip_reason='')
    payload = _asset_payload(asset)
    assert payload['has_content'] is True
    assert payload['content_text'] == ''


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
    def test_customers_blocked(self, admin_client):
        r = _get(admin_client, '/api/customers', '8.8.8.8')
        assert r.status_code == 403
        assert r.get_json()['code'] == 1

    def test_devices_allowed(self, admin_client):
        r = _get(admin_client, '/api/devices', '8.8.8.8')
        assert r.status_code == 200

    def test_users_blocked(self, admin_client):
        r = _get(admin_client, '/api/users', '8.8.8.8')
        assert r.status_code == 403

    def test_system_overview_blocked(self, admin_client):
        """系统管理（含通知渠道配置）为内网管理项"""
        r = _get(admin_client, '/api/system/overview', '8.8.8.8')
        assert r.status_code == 403

    def test_ticket_export_allowed(self, admin_client):
        r = admin_client.post('/api/tickets/export', json={}, headers={'X-Real-IP': '8.8.8.8'})
        assert r.status_code == 200

    def test_ticket_delete_allowed(self, admin_client, app):
        with app.app_context():
            from models import Ticket
            db.session.add(Ticket(number='WO-X-1', title='t', customer_id=None))
            db.session.commit()
            tid = Ticket.query.filter_by(number='WO-X-1').first().id
        r = admin_client.delete(f'/api/tickets/{tid}', headers={'X-Real-IP': '8.8.8.8'})
        assert r.status_code == 200


@pytest.mark.usefixtures('networks')
class TestExternalAllowed:
    def test_ops_permissions_and_config_bundle_mfa(self, viewer_client, admin_client):
        headers = {'X-Real-IP': '8.8.8.8'}
        denied = viewer_client.delete('/api/task-schedule/999', headers=headers)
        assert denied.status_code == 403
        denied = admin_client.post('/api/inspections/export-bundle',
                                   json={'items': ['config_zip']}, headers=headers)
        assert denied.status_code == 403
        assert 'MFA' in denied.get_json()['message']

    @pytest.mark.parametrize('url', [
        '/api/devices', '/api/devices/tree', '/api/v2/rack/tree',
        '/api/topologies', '/api/topologies/templates', '/api/topologies/editor-meta',
        '/api/dicts/tickets', '/api/dicts/devices', '/api/dicts/rack',
        '/api/meta/entities?entities=device,ticket',
        '/api/task-schedule', '/api/inspections', '/api/inspectors',
        '/api/task-templates', '/api/device-check-templates', '/api/reports',
        '/api/dicts/inspections', '/api/system/inspection-review-checklist',
    ])
    def test_business_dependencies_allowed(self, admin_client, url):
        assert _get(admin_client, url, '8.8.8.8').status_code == 200

    def test_external_password_still_requires_permission(self, viewer_client):
        response = viewer_client.post('/api/v2/devices/999/reveal-password',
                                      headers={'X-Real-IP': '8.8.8.8'}, json={})
        assert response.status_code == 403

    def test_external_config_requires_mfa_and_writes_audit(self, app, admin_client):
        from models import User, Device, DeviceConfigBackup, AuditLog
        from utils.totp import issue_operation_token
        with app.app_context():
            user = User.query.filter_by(username='admin').one()
            user.mfa_enabled = True
            device = Device(device_name='配置守卫设备')
            db.session.add(device)
            db.session.flush()
            backup = DeviceConfigBackup(device_id=device.id, config_content='test-config')
            db.session.add(backup)
            db.session.commit()
            bid = backup.id
            token = issue_operation_token(user.id, user.auth_version)
        headers = {'X-Real-IP': '8.8.8.8'}
        for suffix in ('content', 'download'):
            denied = admin_client.get(f'/api/devices/config-backup/{bid}/{suffix}', headers=headers)
            assert denied.status_code == 403
            assert denied.get_json()['message'] == '需要操作动态码验证'
        assert admin_client.get('/api/devices/config-backup/diff?a=1&b=2', headers=headers).status_code == 403
        allowed = admin_client.get(f'/api/devices/config-backup/{bid}/content',
                                  headers={**headers, 'X-Operation-Token': token})
        assert allowed.status_code == 200
        assert allowed.get_json()['data']['content'] == 'test-config'
        assert 'no-store' in allowed.headers['Cache-Control']
        with app.app_context():
            assert AuditLog.query.filter_by(action='device:config_view').count() == 1

    def test_external_mfa_cannot_be_disabled_by_global_switch(self, app, admin_client):
        from models import User
        from utils.totp import issue_operation_token
        paths = ['/api/devices/999/reveal-password', '/api/v2/devices/999/reveal-password']
        headers = {'X-Real-IP': '8.8.8.8'}
        for path in paths:
            denied = admin_client.post(path, json={}, headers=headers)
            assert denied.status_code == 403
            assert '绑定账号 MFA' in denied.get_json()['message']
        with app.app_context():
            user = User.query.filter_by(username='admin').one()
            user.mfa_enabled = True
            db.session.commit()
            wrong_user_token = issue_operation_token(user.id + 1000, user.auth_version)
        for path in paths:
            denied = admin_client.post(path, json={}, headers={
                **headers, 'X-Operation-Token': wrong_user_token})
            assert denied.status_code == 403
            assert denied.get_json()['message'] == '需要操作动态码验证'

    def test_external_ticket_keeps_selected_customer(self, app, admin_client):
        with app.app_context():
            customer = Customer(name='外网工单客户')
            db.session.add(customer)
            db.session.commit()
            cid = customer.id
        created = admin_client.post('/api/tickets', json={
            'title': '外网报修', 'customer_id': cid,
        }, headers={'X-Real-IP': '8.8.8.8'})
        assert created.status_code == 200
        tid = created.get_json()['data']['id']
        detail = _get(admin_client, f'/api/tickets/{tid}', '8.8.8.8').get_json()['data']
        assert detail['customer_id'] == cid

    @pytest.mark.parametrize('path', [
        '/static/uploads/configs/1/a.cfg', '/static/uploads/inspection_configs/1/a.zip',
        '/static/uploads/topologies/../configs/1/a.cfg', '/api/devices-other',
    ])
    def test_external_config_raw_paths_and_prefix_bypass_blocked(self, admin_client, path):
        assert _get(admin_client, path, '8.8.8.8').status_code in (302, 403)

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


@pytest.mark.usefixtures('networks')
@pytest.mark.parametrize('method', ['GET', 'HEAD'])
def test_external_export_chunk_is_javascript(client, tmp_path, monkeypatch, method):
    dist = tmp_path / 'app'
    assets = dist / 'assets'
    assets.mkdir(parents=True)
    (assets / 'export-Drt8K1iI.js').write_text('export const ok = true;', encoding='utf-8')
    monkeypatch.setattr('blueprints.vue_api._app_dist_dir', lambda: str(dist))
    response = client.open('/app/assets/export-Drt8K1iI.js', method=method,
                           environ_overrides={'REMOTE_ADDR': '8.8.8.8'})
    assert response.status_code == 200
    assert 'javascript' in response.content_type
    assert 'Location' not in response.headers
    if method == 'GET':
        assert response.data == b'export const ok = true;'
    from utils.access_guard import _external_allowed
    assert not _external_allowed('/api/devices/export', 'GET')
    assert not _external_allowed('/static/uploads/configs/export.txt', 'GET')


class TestUploadedStaticFiles:
    def test_anonymous_is_404_and_authenticated_is_allowed(
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
        assert authenticated.status_code == 200
        assert authenticated.data == b'protected'


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
        """外网侧栏显示工单及三项资产功能。"""
        r = _get(admin_client, '/api/auth/sidebar-groups', '8.8.8.8')
        groups = r.get_json()['data']
        keys = [g['key'] for g in groups]
        assert keys == ['workbench', 'ops', 'dev']
        asset = next(g for g in groups if g['key'] == 'dev')
        assert {c['url'] for c in asset['children']} == {'/app/devices', '/app/rack', '/app/topologies'}
        ops = next(g for g in groups if g['key'] == 'ops')
        urls = [c['url'] for c in ops['children']]
        assert {'/app/tickets', '/app/faults', '/app/task-schedule',
                '/app/inspectors', '/app/inspections', '/app/task-templates',
                '/app/device-check-templates', '/app/reports'} == {u.rstrip('/') for u in urls}
        wb = next(g for g in groups if g['key'] == 'workbench')
        assert wb['single_link']['url'].endswith('/tickets')


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
        # 外网仍保留工单关联 ID，客户附加信息维持最小集。
        r = _get(admin_client, f'/api/tickets/{tid}', '8.8.8.8')
        d = r.get_json()['data']
        assert d['customer_id'] == cid
        assert d['customer'] == {'name': '脱敏客户', 'office': 'A栋',
                                 'office_room': '101', 'map_location': 'xx,xx'}
        assert d['related_device_id'] is None
        # 内网：customer 字段完整、customer 最小集为 None
        r2 = _get(admin_client, f'/api/tickets/{tid}', '10.1.2.3')
        d2 = r2.get_json()['data']
        assert d2['customer_id'] == cid
        assert d2['customer'] is None
