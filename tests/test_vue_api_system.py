# -*- coding: utf-8 -*-
"""P4 系统域 Vue API：用户/RBAC / 部门 / 审计日志 / 系统概览"""

from models import db, User, Department, AuditLog


class TestUserApi:
    def test_list_requires_admin(self, op_client):
        assert op_client.get('/api/users').status_code == 403

    def test_list(self, admin_client):
        r = admin_client.get('/api/users')
        body = r.get_json()
        assert body['code'] == 0
        data = body['data']
        assert len(data['users']) >= 4  # admin/op/sales/viewer
        assert 'admin' in data['roles']

    def test_create_update_delete(self, admin_client, app):
        r = admin_client.post('/api/users', json={
            'username': 'newuser', 'password': 'pass123', 'realname': '新用户',
            'role': 'operator', 'is_active': True})
        assert r.status_code == 200
        with app.app_context():
            u = User.query.filter_by(username='newuser').first()
            assert u is not None and u.role == 'operator'
            assert AuditLog.query.filter_by(action='user:create').count() >= 1
            uid = u.id
        r = admin_client.put(f'/api/users/{uid}', json={
            'username': 'newuser2', 'realname': '改名', 'role': 'viewer', 'is_active': False})
        assert r.status_code == 200
        with app.app_context():
            assert User.query.get(uid).role == 'viewer'
            assert User.query.get(uid).is_active is False
        r = admin_client.delete(f'/api/users/{uid}')
        assert r.status_code == 200
        with app.app_context():
            assert User.query.get(uid) is None

    def test_duplicate_username(self, admin_client):
        r = admin_client.post('/api/users', json={'username': 'admin'})
        assert r.status_code == 400

    def test_cannot_delete_self(self, admin_client):
        r = admin_client.delete('/api/users/1')
        assert r.status_code == 400


class TestDepartmentApi:
    def test_list(self, admin_client):
        r = admin_client.get('/api/departments')
        assert r.get_json()['code'] == 0

    def test_crud(self, admin_client, app):
        r = admin_client.post('/api/departments', json={'name': '测试部门'})
        assert r.status_code == 200
        did = r.get_json()['data']['id']
        admin_client.put(f'/api/departments/{did}', json={'name': '测试部门2'})
        with app.app_context():
            assert Department.query.get(did).name == '测试部门2'
        admin_client.delete(f'/api/departments/{did}')
        with app.app_context():
            assert Department.query.get(did) is None

    def test_delete_with_member_rejected(self, admin_client, app):
        with app.app_context():
            d = Department(name='有人部门')
            db.session.add(d)
            db.session.commit()
            did = d.id
            op = User.query.filter_by(username='op').first()
            op.department_id = did
            db.session.commit()
        r = admin_client.delete(f'/api/departments/{did}')
        assert r.status_code == 400


class TestAuditApi:
    def test_requires_admin(self, op_client):
        assert op_client.get('/api/audit-logs').status_code == 403

    def test_audit_recorded_on_reveal(self, op_client, admin_client, app):
        """设备密码 reveal 写审计（op 执行 → admin 可查）"""
        with app.app_context():
            from models import Customer, Device
            from utils.crypto import encrypt_password
            c = Customer(name='审计客户')
            db.session.add(c)
            db.session.flush()
            d = Device(customer_id=c.id, device_name='审计设备',
                       password_encrypted=encrypt_password('x'))
            db.session.add(d)
            db.session.commit()
            did = d.id
        op_client.post(f'/api/v2/devices/{did}/reveal-password')
        with app.app_context():
            log = AuditLog.query.filter_by(action='device:reveal').first()
            assert log is not None
            assert log.username == 'op'
        r = admin_client.get('/api/audit-logs', query_string={'action': 'device:reveal'})
        data = r.get_json()['data']
        assert data['total'] >= 1

    def test_query_filters(self, admin_client, app):
        with app.app_context():
            db.session.add(AuditLog(username='op', action='ticket:delete',
                                   target_type='ticket', target_id=1, detail='删单', ip='1.1.1.1'))
            db.session.commit()
        r = admin_client.get('/api/audit-logs', query_string={'username': 'op'})
        assert r.get_json()['data']['total'] >= 1
        r = admin_client.get('/api/audit-logs', query_string={'action': 'ticket:delete'})
        assert r.get_json()['data']['total'] >= 1
        r = admin_client.get('/api/audit-logs', query_string={'target_type': 'ticket'})
        assert r.get_json()['data']['total'] >= 1
        r = admin_client.get('/api/dicts/audit')
        assert 'ticket:delete' in r.get_json()['data']['actions']


class TestSystemOverview:
    def test_overview(self, admin_client):
        r = admin_client.get('/api/system/overview')
        body = r.get_json()
        assert body['code'] == 0
        data = body['data']
        assert data['stats']['user'] >= 4
        assert data['version']  # VERSION 文件
