# -*- coding: utf-8 -*-
"""V24 多角色：role_codes 创建/更新/回显、权限并集、审核岗位（用户级 grant）、提交审核通知"""
import pytest

from models import (db, User, Department, Notification, Role, RolePermission, SystemSetting,
                    Ticket, Customer, Inspection)


@pytest.fixture()
def seed(app):
    """一次 context 内完成全部播种，避免嵌套 context 触发 SQLite 写锁"""
    with app.app_context():
        head = User.create_with_password(
            username='dept_head', password='test123456', realname='部门主管',
            role='operator')
        db.session.add(head)
        db.session.flush()
        dept = Department(name='测试部', head_id=head.id)
        db.session.add(dept)
        db.session.flush()
        pure = User.create_with_password(
            username='pure_op', password='test123456', realname='纯工程师',
            role='operator', roles=['operator'])
        db.session.add(pure)
        c = Customer(name='多角色测试客户')
        db.session.add(c)
        db.session.flush()
        i1 = Inspection(title='纯工程师巡检', customer_id=c.id, inspection_date=None,
                        inspector='pure_op', inspector_name='pure_op',
                        overall_status='草稿', review_status='',
                        content_json='[{"name": "电源检查"}]')
        i2 = Inspection(title='授权工程师巡检', customer_id=c.id, inspection_date=None,
                        inspector='op', inspector_name='op',
                        overall_status='草稿', review_status='',
                        content_json='[{"name": "电源检查"}]')
        i3 = Inspection(title='通知巡检', customer_id=c.id, inspection_date=None,
                        inspector='op', inspector_name='op',
                        overall_status='草稿', review_status='',
                        content_json='[{"name": "电源检查"}]')
        db.session.add_all([i1, i2, i3])
        db.session.commit()
        yield {
            'head_id': head.id, 'dept_id': dept.id, 'pure_id': pure.id,
            'customer_id': c.id, 'i1': i1.id, 'i2': i2.id, 'i3': i3.id,
        }


class TestMultiRoleModel:
    def test_create_with_roles_syncs_role_codes(self, app):
        with app.app_context():
            u = User.create_with_password(
                username='mr1', password='x', realname='MR1', roles=['sales', 'operator'])
            db.session.add(u)
            db.session.commit()
            assert u.role_codes_list() == ['sales', 'operator']
            assert u.role == 'sales'  # 首个 = 主角色
            assert u.has_role('operator')
            assert not u.has_role('viewer')

    def test_set_role_codes_updates_primary(self, app):
        with app.app_context():
            u = User.create_with_password(username='mr2', password='x', realname='MR2', roles=['operator'])
            db.session.add(u)
            db.session.commit()
            u.set_role_codes(['viewer', 'operator'])
            db.session.commit()
            assert u.role == 'viewer'
            assert u.role_codes_list() == ['viewer', 'operator']

    def test_is_admin_true_only_with_admin_role(self, app):
        with app.app_context():
            u = User.create_with_password(username='mr3', password='x', realname='MR3', roles=['operator'])
            db.session.add(u)
            db.session.commit()
            assert not u.is_admin
            u.set_role_codes(['admin', 'operator'])
            db.session.commit()
            assert u.is_admin

    def test_legacy_row_role_codes_empty_fallback(self, app):
        with app.app_context():
            u = User(username='legacy', password='x', role='operator', role_codes='')
            db.session.add(u)
            db.session.commit()
            assert u.role_codes_list() == ['operator']

    def test_unknown_role_fails_closed(self, app):
        with app.app_context():
            from utils.permission import get_user_permissions
            u = User.create_with_password(
                username='unknown_role_user', password='x', roles=['not_exists'])
            db.session.add(u)
            db.session.commit()
            assert get_user_permissions(u) == []

    def test_external_role_version_change_invalidates_local_cache(self, app):
        with app.app_context():
            import utils.permission as permission
            viewer = User.query.filter_by(username='viewer').first()
            assert 'device:view' in permission.get_user_permissions(viewer)
            role = Role.query.filter_by(code='viewer').first()
            RolePermission.query.filter_by(
                role_id=role.id, permission_code='device:view').delete()
            version = SystemSetting.query.get('rbac_cache_version')
            version.value = 'simulated-other-worker-version'
            db.session.commit()

            permission._role_version_checked_at = 0
            assert 'device:view' not in permission.get_user_permissions(viewer)

    def test_disabled_admin_role_does_not_keep_admin_shortcut(self, app):
        with app.app_context():
            import utils.permission as permission
            admin = User.query.filter_by(username='admin').first()
            role = Role.query.filter_by(code='admin').first()
            role.is_active = False
            permission.bump_role_cache_version()
            db.session.commit()
            permission._role_version_checked_at = 0
            assert admin.is_admin is False
            assert permission.get_user_permissions(admin) == []


class TestMultiRoleApi:
    def test_create_and_echo_roles(self, admin_client):
        r = admin_client.post('/api/users', json={
            'username': 'mr_api', 'password': 'StrongPass123!', 'realname': 'MR',
            'roles': ['operator', 'sales'], 'is_active': True})
        assert r.get_json()['code'] == 0
        r = admin_client.get('/api/users?search=mr_api')
        items = r.get_json()['data']['users']
        assert items and items[0]['roles'] == ['operator', 'sales']
        assert items[0]['role'] == 'operator'

    def test_update_roles(self, admin_client):
        admin_client.post('/api/users', json={
            'username': 'mr_upd', 'password': 'StrongPass123!', 'realname': 'MU',
            'roles': ['viewer'], 'is_active': True})
        r = admin_client.get('/api/users?search=mr_upd')
        uid = r.get_json()['data']['users'][0]['id']
        r = admin_client.put(f'/api/users/{uid}', json={
            'username': 'mr_upd', 'roles': ['operator', 'viewer']})
        assert r.get_json()['code'] == 0
        r = admin_client.get('/api/users?search=mr_upd')
        u = r.get_json()['data']['users'][0]
        assert u['roles'] == ['operator', 'viewer']
        assert u['role'] == 'operator'

    def test_create_roles_invalid(self, admin_client):
        r = admin_client.post('/api/users', json={
            'username': 'mr_bad', 'password': 'StrongPass123!', 'realname': 'MB',
            'roles': [], 'is_active': True})
        assert r.status_code == 400
        r = admin_client.post('/api/users', json={
            'username': 'mr_bad2', 'password': 'StrongPass123!', 'realname': 'MB2',
            'roles': ['not_exists'], 'is_active': True})
        assert r.status_code == 400

    def test_me_returns_roles_and_union_permissions(self, app, client):
        with app.app_context():
            u = User.query.filter_by(username='sales').first()
            u.set_role_codes(['sales', 'operator'])
            db.session.commit()
        r = client.post('/api/auth/login', json={'username': 'sales', 'password': 'test123456'})
        assert r.status_code == 200
        r = client.get('/api/auth/me')
        d = r.get_json()['data']
        assert 'sales' in d['roles'] and 'operator' in d['roles']
        perms = set(d['permissions'])
        assert 'sales:edit' in perms and 'device:edit' in perms  # 并集

    def test_admin_role_in_union_shortcuts_all(self, app, admin_client):
        with app.app_context():
            u = User.query.filter_by(username='viewer').first()
            u.set_role_codes(['viewer', 'admin'])
            db.session.commit()
        r = admin_client.get('/api/roles')
        assert r.status_code == 200  # admin 判定通过（权限并集短路）

    def test_role_delete_guard_counts_role_codes(self, admin_client, app):
        with app.app_context():
            rid = Role.query.filter_by(code='sales').first().id
            u = User.query.filter_by(username='viewer').first()
            u.set_role_codes(['viewer', 'sales'])
            db.session.commit()
        r = admin_client.delete(f'/api/roles/{rid}')
        assert r.status_code == 400  # viewer 的 role_codes 含 sales，不可删


class TestReviewRole:
    def test_operator_role_no_review_perms(self, app):
        """operator 角色模板已移除 review（REMOVE_ROLE_PERMS 清理）"""
        with app.app_context():
            op_role = Role.query.filter_by(code='operator').first()
            codes = {rp.permission_code for rp in op_role.role_perms}
            assert 'inspection:review' not in codes
            assert 'ticket:review' not in codes
            # conftest 用户级 grant 保留 op 审核能力（不动角色模板）
            op = User.query.filter_by(username='op').first()
            granted = {up.permission_code for up in op.extra_permissions}
            assert 'inspection:review' in granted

    def test_pure_operator_cannot_review(self, app, client, seed):
        """无 grant 的纯 operator 用户审核 403"""
        r = client.post('/api/auth/login', json={'username': 'pure_op', 'password': 'test123456'})
        assert r.status_code == 200
        r = client.post(f"/api/inspections/{seed['i1']}/review", json={'approved': True})
        assert r.status_code == 403

    def test_granted_operator_reviews_ok(self, app, op_client, seed):
        """conftest 用户级 grant 后 op 可审核（inspection:review 生效）"""
        r = op_client.post(f"/api/inspections/{seed['i2']}/submit", json={})
        assert r.get_json()['code'] == 0
        r = op_client.post(f"/api/inspections/{seed['i2']}/review", json={'approved': True})
        assert r.status_code != 403  # 有权限 → 进入业务逻辑（结果非权限拒绝）


class TestReviewNotify:
    def test_ticket_submit_notifies_dept_head_and_admin(self, app, admin_client, seed):
        # admin 挂到测试部：提交审核时通知"提交人部门负责人 + 全部 admin"（admin 自己跳过）
        with app.app_context():
            admin = User.query.filter_by(username='admin').first()
            admin.department_id = seed['dept_id']
            db.session.commit()
        r = admin_client.post('/api/tickets', json={
            'title': '通知测试工单', 'customer_id': seed['customer_id'], 'priority': '中'})
        assert r.get_json()['code'] == 0
        tid = r.get_json()['data']['id']
        with app.app_context():
            t = db.session.get(Ticket, tid)
            t.assigned_to = 'admin'
            t.status = '处理中'
            db.session.commit()
        # admin 提交审核（admin 是提交人，跳过自己；部门主管应收到）
        r = admin_client.post(f'/api/tickets/{tid}/action', json={'action': 'submit', 'remark': '处理完毕'})
        assert r.get_json()['code'] == 0
        with app.app_context():
            head_msgs = Notification.query.filter_by(user_id=seed['head_id'], category='ticket').all()
            assert head_msgs, '部门主管应收到工单提交通知'
            assert any('提交审核' in n.title for n in head_msgs)

    def test_inspection_submit_notifies_admin_when_no_dept(self, app, op_client, seed):
        r = op_client.post(f"/api/inspections/{seed['i3']}/submit", json={})
        assert r.get_json()['code'] == 0
        with app.app_context():
            admin_msgs = Notification.query.filter_by(category='inspection').all()
            assert admin_msgs, '无部门时 admin 应收到巡检提交通知'
