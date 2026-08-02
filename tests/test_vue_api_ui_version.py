# -*- coding: utf-8 -*-
"""界面版本切换：配置读写 / 侧栏映射 / SSR+Vue 双端入口"""

from utils.ui_version import set_ui_version, get_ui_version, sidebar_url


class TestUiVersionCore:
    def test_default_ssr(self, app):
        with app.app_context():
            assert get_ui_version() == 'ssr'

    def test_set_and_get(self, app):
        with app.app_context():
            set_ui_version('vue')
            assert get_ui_version() == 'vue'
            set_ui_version('ssr')
            assert get_ui_version() == 'ssr'

    def test_sidebar_url_mapping(self, app):
        with app.app_context():
            set_ui_version('vue')
            assert sidebar_url('/devices') == '/app/devices'
            assert sidebar_url('/tickets') == '/app/tickets'
            assert sidebar_url('/') == '/app/'
            # query 保留
            assert sidebar_url('/knowledge-base?category=故障处置') == '/app/knowledge-base?category=故障处置'
            # 未迁移保持原样
            assert sidebar_url('/inspection-templates') == '/inspection-templates'
            assert sidebar_url('/ai-config') == '/ai-config'
            set_ui_version('ssr')
            assert sidebar_url('/devices') == '/devices'


class TestUiVersionApi:
    def test_get_requires_login(self, client):
        assert client.get('/api/system/ui-version').status_code == 401

    def test_get(self, admin_client):
        r = admin_client.get('/api/system/ui-version')
        body = r.get_json()
        assert body['code'] == 0
        assert body['data']['version'] in ('vue', 'ssr')
        assert body['data']['vue_migrated_count'] > 0

    def test_set_requires_admin(self, op_client):
        r = op_client.put('/api/system/ui-version', json={'version': 'vue'})
        assert r.status_code == 403

    def test_set_and_audit(self, admin_client, app):
        r = admin_client.put('/api/system/ui-version', json={'version': 'vue'})
        assert r.status_code == 200
        assert r.get_json()['data']['version'] == 'vue'
        with app.app_context():
            from models import AuditLog
            assert AuditLog.query.filter_by(action='system:ui_version').count() >= 1
            # 切回
            admin_client.put('/api/system/ui-version', json={'version': 'ssr'})
            assert get_ui_version() == 'ssr'

    def test_invalid_version(self, admin_client):
        r = admin_client.put('/api/system/ui-version', json={'version': 'x'})
        assert r.status_code == 400


class TestSsrSidebarIntegration:
    def test_sidebar_links_follow_ui_version(self, admin_client, app):
        """vue 模式：SSR 侧栏已迁移链接带 /app 前缀"""
        with app.app_context():
            set_ui_version('vue')
        r = admin_client.get('/')
        body = r.data.decode('utf-8')
        # 首页重定向到 /app/
        assert r.status_code == 302
        assert r.headers.get('Location', '').endswith('/app/')
        with app.app_context():
            set_ui_version('ssr')
        r = admin_client.get('/')
        assert r.status_code == 200
        body = r.data.decode('utf-8')
        assert '/app/devices' not in body
        assert 'href="/devices"' in body
