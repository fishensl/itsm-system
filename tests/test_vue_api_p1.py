# -*- coding: utf-8 -*-
"""P1 Vue 后端 API 契约：认证 / 侧栏 / Dashboard / SPA 静态服务"""



class TestVueAuthApi:
    def test_login_success(self, client, app):
        r = client.post('/api/auth/login', json={'username': 'admin', 'password': 'test123456'})
        assert r.status_code == 200
        body = r.get_json()
        assert body['code'] == 0
        assert body['data']['user']['role'] == 'admin'
        assert 'device:view' in body['data']['user']['permissions']

    def test_login_wrong_password(self, client):
        r = client.post('/api/auth/login', json={'username': 'admin', 'password': 'bad'})
        assert r.status_code == 401
        assert r.get_json()['code'] == 1

    def test_login_empty(self, client):
        r = client.post('/api/auth/login', json={})
        assert r.status_code == 401

    def test_me_requires_login(self, client):
        assert client.get('/api/auth/me').status_code == 401

    def test_me_returns_permissions(self, op_client):
        r = op_client.get('/api/auth/me')
        body = r.get_json()
        assert body['code'] == 0
        assert body['data']['permissions']  # 非空
        assert 'device:reveal' in body['data']['permissions']

    def test_logout_flow(self, op_client):
        assert op_client.get('/api/auth/me').status_code == 200
        op_client.post('/api/auth/logout')
        assert op_client.get('/api/auth/me').status_code == 401

    def test_inactive_user_rejected(self, client, app):
        from models import db, User
        with app.app_context():
            db.session.add(User(username='banned', password='x', role='viewer',
                                is_active=False))
            db.session.commit()
        r = client.post('/api/auth/login', json={'username': 'banned', 'password': 'x'})
        assert r.status_code == 403


class TestVueSidebarApi:
    def test_groups_permission_filtered(self, viewer_client):
        """viewer 只能看到有权限的分组与子项"""
        r = viewer_client.get('/api/auth/sidebar-groups')
        body = r.get_json()
        assert body['code'] == 0
        groups = body['data']
        assert groups  # 至少工作台
        # viewer 看不到 user:view 等管理入口（如用户管理子项）
        all_urls = []
        for g in groups:
            if g.get('single_link'):
                all_urls.append(g['single_link']['url'])
            for c in g.get('children', []):
                all_urls.append(c['url'])
        assert '/users' not in all_urls
        assert '/devices' in all_urls  # viewer 有 device:view

    def test_admin_sees_all_groups(self, admin_client):
        r = admin_client.get('/api/auth/sidebar-groups')
        assert len(r.get_json()['data']) >= 8

    def test_icons_mapped_to_element_plus(self, admin_client):
        """bi-* 图标映射为 Element Plus 图标名（前端 <component :is> 用）"""
        r = admin_client.get('/api/auth/sidebar-groups')
        for g in r.get_json()['data']:
            assert not g['icon'].startswith('bi-'), f'未映射图标: {g["icon"]}'
            if g.get('single_link'):
                assert not g['single_link']['icon'].startswith('bi-')
            for c in g.get('children', []):
                assert not c['icon'].startswith('bi-')


class TestVueDashboardApi:
    def test_overview_shape(self, admin_client):
        r = admin_client.get('/api/dashboard/overview')
        body = r.get_json()
        assert body['code'] == 0
        data = body['data']
        assert 'metrics' in data and len(data['metrics']) >= 8
        assert 'my_tasks' in data
        assert 'quick_entries' in data and data['quick_entries']
        assert 'expiring_devices' in data
        assert 'recent_inspections' in data
        assert 'device_type_stats' in data

    def test_sales_role_entries(self, sales_client):
        r = sales_client.get('/api/dashboard/overview')
        data = r.get_json()['data']
        titles = [q['title'] for q in data['quick_entries']]
        assert '商机跟进' in titles  # 销售角色入口

    def test_requires_login(self, client):
        assert client.get('/api/dashboard/overview').status_code == 401


class TestVueSpaStatic:
    def test_index_html(self, admin_client):
        r = admin_client.get('/app/')
        assert r.status_code == 200
        assert 'id="app"' in r.data.decode('utf-8', 'ignore')

    def test_deep_route_fallback(self, admin_client):
        """history 路由回退 index.html"""
        r = admin_client.get('/app/devices/123')
        assert r.status_code == 200
        assert 'id="app"' in r.data.decode('utf-8', 'ignore')
