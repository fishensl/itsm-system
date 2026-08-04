# -*- coding: utf-8 -*-
"""界面版本切换：配置读写 / 侧栏映射 / SSR+Vue 双端入口"""

from utils.ui_version import set_ui_version, get_ui_version, sidebar_url


class TestUiVersionCore:
    def test_default_vue(self, app):
        with app.app_context():
            assert get_ui_version() == 'vue'

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
            # 备件三入口映射到 spare-parts 标签页
            assert sidebar_url('/spare-stocks') == '/app/spare-parts?tab=stocks'
            assert sidebar_url('/purchase-orders') == '/app/spare-parts?tab=purchases'
            assert sidebar_url('/sales-orders') == '/app/spare-parts?tab=sales'
            # 销售四入口映射到 sales 标签页
            assert sidebar_url('/opportunities') == '/app/sales?tab=opps'
            assert sidebar_url('/quotations') == '/app/sales?tab=quotations'
            assert sidebar_url('/contracts') == '/app/sales?tab=contracts'
            assert sidebar_url('/projects') == '/app/sales?tab=projects'
            # 系统概览 / 新增知识 / 工具入口（工具按 tool 区分）
            assert sidebar_url('/system') == '/app/system/overview'
            assert sidebar_url('/knowledge-base/add') == '/app/knowledge-base'
            assert sidebar_url('/tools/network') == '/app/tools?tool=network'
            assert sidebar_url('/tools/convert') == '/app/tools?tool=convert'
            assert sidebar_url('/tools/packet') == '/app/tools?tool=packet'
            # 用户/部门入口映射到 system/users 标签页
            assert sidebar_url('/users') == '/app/system/users?tab=users'
            assert sidebar_url('/departments/') == '/app/system/users?tab=departments'
            # 映射值自带 query 时原始 query 用 & 拼接
            assert sidebar_url('/spare-stocks?search=x') == '/app/spare-parts?tab=stocks&search=x'
            # 未迁移保持原样
            assert sidebar_url('/inspection-templates') == '/inspection-templates'
            assert sidebar_url('/no-such-page') == '/no-such-page'
            # 阶段 1-3 新迁移入口
            assert sidebar_url('/ai-config') == '/app/ai-config'
            assert sidebar_url('/inspectors') == '/app/inspectors'
            assert sidebar_url('/task-schedule/') == '/app/task-schedule'
            set_ui_version('ssr')
            assert sidebar_url('/devices') == '/devices'

    def test_sidebar_url_force(self, app):
        """force=True：与系统界面版本无关，无条件映射（Vue SPA 专用 API）"""
        with app.app_context():
            set_ui_version('ssr')
            assert sidebar_url('/devices', force=True) == '/app/devices'
            assert sidebar_url('/spare-stocks', force=True) == '/app/spare-parts?tab=stocks'
            assert sidebar_url('/ai-config', force=True) == '/app/ai-config'
            assert sidebar_url('/inspection-templates', force=True) == '/inspection-templates'


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

    def test_ssr_render_does_not_mutate_sidebar_api(self, admin_client, app):
        """vue 模式渲染 SSR 页面后，/api/auth/sidebar-groups 仍一致（共享配置不被污染）"""
        with app.app_context():
            set_ui_version('vue')
        assert admin_client.get('/').status_code == 302
        assert admin_client.get('/devices').status_code == 200
        r = admin_client.get('/api/auth/sidebar-groups')
        body = r.get_json()
        assert body['code'] == 0
        urls = []
        for g in body['data']:
            if g.get('single_link'):
                urls.append(g['single_link']['url'])
            for c in g.get('children', []):
                urls.append(c['url'])
        # 已迁移页面稳定返回 /app 前缀；未迁移保持原样（不随 SSR 渲染漂移）
        assert '/app/devices' in urls
        assert '/devices' not in urls
        assert '/app/inspectors' in urls
        assert '/app/task-schedule' in urls
