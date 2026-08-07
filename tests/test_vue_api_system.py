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

    def test_region_ids_roundtrip(self, admin_client, app):
        """用户负责区域（多选）：创建/更新/列表/me 全链路"""
        with app.app_context():
            from models import Region
            city = Region(name='测试市'); db.session.add(city); db.session.flush()
            dist = Region(name='测试区', parent_id=city.id)
            db.session.add(dist); db.session.commit()
            city_id, dist_id = city.id, dist.id
        # 创建带区域
        r = admin_client.post('/api/users', json={
            'username': 'eng1', 'password': 'pass123', 'realname': '驻场工程师',
            'role': 'operator', 'region_ids': [city_id, dist_id]})
        assert r.status_code == 200
        with app.app_context():
            u = User.query.filter_by(username='eng1').first()
            assert {x.id for x in u.regions} == {city_id, dist_id}
            uid = u.id
        # 列表回显
        r = admin_client.get('/api/users')
        row = next(x for x in r.get_json()['data']['users'] if x['username'] == 'eng1')
        assert row['region_ids'] == [city_id, dist_id]
        assert row['region_names'] == ['测试市', '测试区']
        # 更新清空
        r = admin_client.put(f'/api/users/{uid}', json={'username': 'eng1', 'region_ids': []})
        assert r.status_code == 200
        with app.app_context():
            assert User.query.get(uid).regions == []
        # me 回显
        c = app.test_client()
        c.post('/login', data={'username': 'eng1', 'password': 'pass123'})
        r = c.get('/api/auth/me')
        assert r.get_json()['data']['region_ids'] == []

    def test_customer_ids_roundtrip(self, admin_client, app):
        """工程师直接关联客户（多对多）：创建/更新/列表/me 全链路"""
        with app.app_context():
            from models import Customer
            c1 = Customer(name='关联客户A')
            c2 = Customer(name='关联客户B')
            db.session.add_all([c1, c2])
            db.session.commit()
            c1_id, c2_id = c1.id, c2.id
        # 创建带关联客户
        r = admin_client.post('/api/users', json={
            'username': 'eng2', 'password': 'pass123', 'realname': '驻场工程师',
            'role': 'operator', 'customer_ids': [c1_id, c2_id]})
        assert r.status_code == 200
        with app.app_context():
            u = User.query.filter_by(username='eng2').first()
            assert {x.id for x in u.customers} == {c1_id, c2_id}
            uid = u.id
        # 列表回显
        r = admin_client.get('/api/users')
        row = next(x for x in r.get_json()['data']['users'] if x['username'] == 'eng2')
        assert row['customer_ids'] == [c1_id, c2_id]
        assert row['customer_names'] == ['关联客户A', '关联客户B']
        # 更新清空
        r = admin_client.put(f'/api/users/{uid}', json={'username': 'eng2', 'customer_ids': []})
        assert r.status_code == 200
        with app.app_context():
            assert User.query.get(uid).customers == []
        # me 回显
        c = app.test_client()
        c.post('/login', data={'username': 'eng2', 'password': 'pass123'})
        r = c.get('/api/auth/me')
        assert r.get_json()['data']['customer_ids'] == []

    def test_role_name_display(self, admin_client, app):
        """自定义角色在用户列表显示名称而非代码"""
        with app.app_context():
            from models import Role
            db.session.add(Role(code='ops_zhuchang', name='驻场工程师',
                                is_system=False, is_active=True))
            db.session.commit()
        r = admin_client.post('/api/users', json={
            'username': 'eng3', 'password': 'pass123', 'role': 'ops_zhuchang'})
        assert r.status_code == 200
        r = admin_client.get('/api/users')
        data = r.get_json()['data']
        row = next(x for x in data['users'] if x['username'] == 'eng3')
        assert row['role'] == 'ops_zhuchang'
        assert row['role_name'] == '驻场工程师'
        assert data['role_names']['ops_zhuchang'] == '驻场工程师'
        assert data['role_names']['admin'] == '系统管理员'

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
        assert data['stats']['user_active'] >= 4
        assert data['stats']['user_total'] >= data['stats']['user_active']
        assert data['version']  # VERSION 文件
        # 最近用户（SSR 同模块结构）
        assert 0 < len(data['recent_users']) <= 5
        assert set(data['recent_users'][0]) == {'name', 'username', 'role'}

    def test_repair_device_counts(self, admin_client, app):
        """修复客户 device_count 冗余快照（快照与 devices 表不一致时）"""
        from models import Customer, Device
        with app.app_context():
            c = Customer(name='快照残留客户')
            db.session.add(c)
            db.session.flush()
            db.session.add(Device(customer_id=c.id, device_name='D1'))
            db.session.add(Device(customer_id=c.id, device_name='D2'))
            db.session.commit()
            c.device_count = 99  # 人为制造不一致
            db.session.commit()
            cid = c.id
        r = admin_client.post('/api/system/repair-device-counts')
        assert r.status_code == 200
        data = r.get_json()['data']
        assert data['fixed'] >= 1
        with app.app_context():
            c = Customer.query.get(cid)
            assert c.device_count == 2
            assert AuditLog.query.filter_by(action='system:repair_device_counts').count() >= 1

    def test_repair_requires_permission(self, op_client):
        """operator 无 system:repair 权限码"""
        assert op_client.post('/api/system/repair-device-counts').status_code == 403

    def test_overview_deploy_info(self, admin_client):
        """部署信息：系统/组件/数据库/资源占用（与 SSR 系统概览共用采集）"""
        r = admin_client.get('/api/system/overview')
        data = r.get_json()['data']
        deploy = data['deploy']
        assert set(deploy) == {'sys_info', 'components', 'db_info', 'resources'}
        assert deploy['sys_info']['os_name']
        assert deploy['sys_info']['python_version']
        assert deploy['components']['Flask']
        assert deploy['components']['psutil']
        assert deploy['db_info']['engine']
        res = deploy['resources']
        assert res['available'] is True
        assert isinstance(res['cpu_percent'], (int, float))
        assert res['memory_total_gb'] > 0
        assert res['disk_total_gb'] > 0
        assert res['process_pid'] > 0
