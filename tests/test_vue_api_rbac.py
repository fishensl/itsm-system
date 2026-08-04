# -*- coding: utf-8 -*-
"""Vue API：权限管理（角色 CRUD / 权限矩阵 / 用户级覆盖）"""
from models import db, Role, User, UserPermission


class TestRolesApi:
    def test_list_matrix(self, admin_client):
        r = admin_client.get('/api/roles')
        assert r.get_json()['code'] == 0
        d = r.get_json()['data']
        assert len(d['perm_map']) > 50
        codes = {x['code'] for x in d['roles']}
        assert 'admin' in codes and 'operator' in codes
        admin_role = next(x for x in d['roles'] if x['code'] == 'admin')
        # admin 短路全量权限
        assert len(admin_role['permissions']) == len(d['perm_map'])

    def test_role_crud(self, admin_client, app):
        r = admin_client.post('/api/roles', json={'code': 'ops_mgr', 'name': '运维主管', 'sort_order': 5})
        assert r.get_json()['code'] == 0
        rid = r.get_json()['data']['id']
        r = admin_client.put(f'/api/roles/{rid}', json={'name': '运维经理', 'sort_order': 6})
        assert r.get_json()['code'] == 0
        with app.app_context():
            role = db.session.get(Role, rid)
            assert role.name == '运维经理'
        r = admin_client.delete(f'/api/roles/{rid}')
        assert r.get_json()['code'] == 0
        with app.app_context():
            assert db.session.get(Role, rid) is None

    def test_role_code_rules(self, admin_client):
        r = admin_client.post('/api/roles', json={'code': '', 'name': 'x'})
        assert r.status_code == 400
        r = admin_client.post('/api/roles', json={'code': 'bad code!', 'name': 'x'})
        assert r.status_code == 400
        r = admin_client.post('/api/roles', json={'code': 'admin', 'name': 'dup'})
        assert r.status_code == 400  # 已存在

    def test_system_role_not_deletable(self, admin_client, app):
        with app.app_context():
            rid = Role.query.filter_by(code='operator').first().id
        r = admin_client.delete(f'/api/roles/{rid}')
        assert r.status_code == 400

    def test_permissions_save_and_cache_invalidate(self, admin_client, app):
        with app.app_context():
            rid = Role.query.filter_by(code='operator').first().id
        r = admin_client.put(f'/api/roles/{rid}/permissions', json={'codes': ['device:view', 'ticket:view']})
        assert r.get_json()['code'] == 0
        with app.app_context():
            role = db.session.get(Role, rid)
            got = {rp.permission_code for rp in role.role_perms}
            assert got == {'device:view', 'ticket:view'}
        r = admin_client.put(f'/api/roles/{rid}/permissions', json={'codes': ['device:view']})
        assert r.get_json()['code'] == 0
        with app.app_context():
            role = db.session.get(Role, rid)
            assert {rp.permission_code for rp in role.role_perms} == {'device:view'}

    def test_admin_permissions_rejected(self, admin_client, app):
        with app.app_context():
            rid = Role.query.filter_by(code='admin').first().id
        r = admin_client.put(f'/api/roles/{rid}/permissions', json={'codes': []})
        assert r.status_code == 400

    def test_permissions(self, op_client, viewer_client):
        assert viewer_client.get('/api/roles').status_code == 403  # 无 permission:view
        assert op_client.get('/api/roles').status_code == 403  # operator 也无 permission:view
        assert op_client.post('/api/roles', json={'code': 'x', 'name': 'y'}).status_code == 403


class TestUserOverrideApi:
    def test_get_save(self, admin_client, app):
        with app.app_context():
            uid = User.query.filter_by(username='viewer').first().id
        r = admin_client.get(f'/api/users/{uid}/permissions')
        assert r.get_json()['code'] == 0
        assert r.get_json()['data']['user']['username'] == 'viewer'
        r = admin_client.put(f'/api/users/{uid}/permissions', json={
            'overrides': {
                'device:view': {'grant_type': 'deny', 'expire_at': '2026-12-31', 'remark': '临时'},
                'ticket:view': {'grant_type': 'grant', 'expire_at': '', 'remark': ''},
            },
        })
        assert r.get_json()['code'] == 0
        with app.app_context():
            ups = UserPermission.query.filter_by(user_id=uid).all()
            assert {u.permission_code: u.grant_type for u in ups} == {
                'device:view': 'deny', 'ticket:view': 'grant'}
        r = admin_client.get(f'/api/users/{uid}/permissions')
        d = r.get_json()['data']
        assert d['overrides']['device:view']['grant_type'] == 'deny'
        assert d['overrides']['device:view']['expire_at'] == '2026-12-31'

    def test_clear_overrides(self, admin_client, app):
        with app.app_context():
            uid = User.query.filter_by(username='viewer').first().id
        admin_client.put(f'/api/users/{uid}/permissions', json={
            'overrides': {'device:view': {'grant_type': 'grant', 'expire_at': '', 'remark': ''}},
        })
        admin_client.put(f'/api/users/{uid}/permissions', json={'overrides': {}})
        with app.app_context():
            assert UserPermission.query.filter_by(user_id=uid).count() == 0

    def test_bad_date_rejected(self, admin_client, app):
        with app.app_context():
            uid = User.query.filter_by(username='viewer').first().id
        r = admin_client.put(f'/api/users/{uid}/permissions', json={
            'overrides': {'device:view': {'grant_type': 'grant', 'expire_at': 'bad', 'remark': ''}},
        })
        assert r.status_code == 400

    def test_permissions(self, op_client, admin_client, app):
        with app.app_context():
            uid = User.query.filter_by(username='viewer').first().id
        assert op_client.get(f'/api/users/{uid}/permissions').status_code == 403  # permission:view 仅 admin
        assert op_client.put(f'/api/users/{uid}/permissions', json={'overrides': {}}).status_code == 403
        assert admin_client.put(f'/api/users/{uid}/permissions', json={'overrides': {}}).status_code == 200
