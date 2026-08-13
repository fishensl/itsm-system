# -*- coding: utf-8 -*-
"""客户与设备数据范围：查看按 scope 裁剪，导出仍需独立权限

- 客户列表/树/详情 → customer:view + 统一数据 scope
- 客户导出 → customer:export（operator 无 → 403）
- 工单/巡检/故障等下拉字典 → 仅返回当前用户关联客户（防枚举名单）
"""
import pytest

from models import db, Customer, Department, Device, User
from utils.customer_scope import customer_dropdown_options


@pytest.fixture()
def seed(app):
    with app.app_context():
        c1 = Customer(name='敏感客户A', contact_person='张三', phone='13800000001')
        c2 = Customer(name='敏感客户B', contact_person='李四', phone='13800000002')
        db.session.add_all([c1, c2])
        db.session.flush()
        d1 = Device(customer_id=c1.id, device_name='范围设备A', ip_address='10.0.0.1')
        d2 = Device(customer_id=c2.id, device_name='范围设备B', ip_address='10.0.0.2')
        db.session.add_all([d1, d2])
        # 给 op 关联 c1（工程师只负责这个客户）
        op = User.query.filter_by(username='op').first()
        op.customers = [c1]
        db.session.commit()
        yield {'c1': c1.id, 'c2': c2.id, 'd1': d1.id, 'd2': d2.id}


class TestOperatorScoped:
    def test_list_only_linked(self, op_client, seed):
        r = op_client.get('/api/customers')
        assert r.status_code == 200
        data = r.get_json()['data']
        assert data['total'] == 1
        assert data['items'][0]['id'] == seed['c1']

    def test_tree_only_linked(self, op_client, seed):
        r = op_client.get('/api/customers/tree')
        assert r.status_code == 200
        assert r.get_json()['data']['total'] == 1

    def test_detail_hides_unlinked_id(self, op_client, seed):
        assert op_client.get(f"/api/customers/{seed['c1']}").status_code == 200
        assert op_client.get(f"/api/customers/{seed['c2']}").status_code == 404

    def test_v2_export_forbidden(self, op_client, seed):
        r = op_client.post('/api/v2/customers/export', json={})
        assert r.status_code == 403

    def test_ssr_export_forbidden(self, op_client, seed):
        """SSR 导出为页面路由：权限不足重定向（非 API 403）"""
        assert op_client.get('/customers/export').status_code == 302

    def test_sidebar_shows_scoped_customer_page(self, op_client, seed):
        r = op_client.get('/api/auth/sidebar-groups')
        keys = [g['key'] for g in r.get_json()['data']]
        assert 'customer' in keys

    def test_router_perm_requires_view(self):
        """前端路由用查看权限，写按钮继续按动作权限控制。"""
        from pathlib import Path
        router = Path(__file__).resolve().parents[1] / 'frontend' / 'src' / 'router' / 'index.ts'
        src = router.read_text(encoding='utf-8')
        assert "path: 'customers'" in src
        assert "perm: 'customer:view'" in src

    def test_device_list_and_direct_id_use_same_scope(self, op_client, seed):
        data = op_client.get('/api/devices').get_json()['data']
        assert data['total'] == 1
        assert data['items'][0]['id'] == seed['d1']
        assert op_client.get(f"/api/devices/{seed['d1']}").status_code == 200
        assert op_client.get(f"/api/devices/{seed['d2']}").status_code == 404

    def test_global_search_does_not_leak_unlinked_customer_or_device(self, op_client, seed):
        device_data = op_client.get('/api/search', query_string={'q': '范围'}).get_json()['data']
        assert [item['id'] for item in device_data['devices']] == [seed['d1']]
        customer_data = op_client.get('/api/search', query_string={'q': '敏感'}).get_json()['data']
        assert [item['id'] for item in customer_data['customers']] == [seed['c1']]


class TestAdminSalesFull:
    def test_admin_list_ok(self, admin_client, seed):
        r = admin_client.get('/api/customers')
        assert r.status_code == 200
        assert r.get_json()['data']['total'] == 2

    def test_sales_list_ok(self, sales_client, seed):
        r = sales_client.get('/api/customers')
        assert r.status_code == 200

    def test_manage_permission_does_not_bypass_self_scope(self, app, sales_client, seed):
        with app.app_context():
            sales = User.query.filter_by(username='sales').first()
            sales.scope = 'self'
            db.session.commit()
        data = sales_client.get('/api/customers').get_json()['data']
        assert data['total'] == 0

    def test_admin_export_ok(self, admin_client, seed):
        r = admin_client.post('/api/v2/customers/export', json={})
        assert r.status_code == 200
        assert r.get_json()['code'] == 0

    def test_sales_export_ok(self, sales_client, seed):
        r = sales_client.post('/api/v2/customers/export', json={})
        assert r.status_code == 200


class TestDropdownScoping:
    def test_op_dropdown_only_linked(self, op_client, seed):
        """工程师下拉仅含关联客户 c1，不含 c2"""
        for url in ('/api/dicts/tickets', '/api/dicts/faults', '/api/dicts/inspections'):
            r = op_client.get(url)
            assert r.status_code == 200
            names = [c['name'] for c in r.get_json()['data']['customers']]
            assert names == ['敏感客户A'], f'{url} 下拉泄露未关联客户: {names}'

    def test_op_device_dicts_scoped(self, op_client, seed):
        r = op_client.get('/api/dicts/devices')
        assert r.status_code == 200
        names = [c['name'] for c in r.get_json()['data']['customers']]
        assert names == ['敏感客户A']

    def test_admin_dropdown_all(self, admin_client, seed):
        r = admin_client.get('/api/dicts/tickets')
        assert r.status_code == 200
        names = [c['name'] for c in r.get_json()['data']['customers']]
        assert len(names) == 2

    def test_scope_util_returns_empty_when_no_link(self, app, seed):
        with app.app_context():
            viewer = User.query.filter_by(username='viewer').first()
            opts = customer_dropdown_options(viewer)
            assert opts == []

    def test_scope_util_manage_returns_all(self, app, seed):
        with app.app_context():
            admin = User.query.filter_by(username='admin').first()
            opts = customer_dropdown_options(admin)
            assert len(opts) == 2
            # 下拉候选不包含敏感字段（电话/地址/联系人）
            assert not any(k in o for o in opts for k in ('phone', 'address', 'contact_person'))
            # 允许合同状态辅助字段（前端过期提示用）
            for o in opts:
                assert o['name']

    def test_department_scope_includes_peer_customer_links(self, app, op_client, seed):
        with app.app_context():
            dept = Department(name='范围部门')
            db.session.add(dept)
            db.session.flush()
            op = User.query.filter_by(username='op').first()
            op.department_id = dept.id
            peer = User.create_with_password(
                username='scope_peer', password='test123456', role='operator',
                realname='同部门工程师', department_id=dept.id)
            peer.customers = [Customer.query.get(seed['c2'])]
            db.session.add(peer)
            db.session.commit()
        data = op_client.get('/api/customers').get_json()['data']
        assert {item['id'] for item in data['items']} == {seed['c1'], seed['c2']}
