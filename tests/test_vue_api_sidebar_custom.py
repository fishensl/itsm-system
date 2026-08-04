# -*- coding: utf-8 -*-
"""Vue API：侧栏自定义（读取/保存/重置）"""
from models import UserDashboardPreference


class TestSidebarCustomApi:
    def test_get_all_groups(self, admin_client):
        r = admin_client.get('/api/system/sidebar')
        assert r.status_code == 200
        body = r.get_json()
        assert body['code'] == 0
        groups = body['data']
        keys = [g['key'] for g in groups]
        assert 'workbench' in keys and 'ops' in keys and 'sys' in keys
        assert all(g['enabled'] is True for g in groups)  # 默认全启用

    def test_save_order_and_enabled(self, admin_client, app):
        r = admin_client.get('/api/system/sidebar')
        groups = r.get_json()['data']
        # 打乱顺序 + 禁用 kb
        new_order = [g for g in reversed(groups)]
        for g in new_order:
            if g['key'] == 'kb':
                g['enabled'] = False
        r = admin_client.put('/api/system/sidebar', json={'groups': new_order})
        assert r.get_json()['code'] == 0
        with app.app_context():
            pref = UserDashboardPreference.query.filter_by(user_id=1).first()
            assert pref is not None and pref.sidebar_json
            import json
            saved = json.loads(pref.sidebar_json)
            assert saved['groups'][0]['key'] == new_order[0]['key']
            kb = next(g for g in saved['groups'] if g['key'] == 'kb')
            assert kb['enabled'] is False
        # 读取反映用户偏好顺序
        r = admin_client.get('/api/system/sidebar')
        got = [g['key'] for g in r.get_json()['data']]
        assert got[0] == new_order[0]['key']
        kb = next(g for g in r.get_json()['data'] if g['key'] == 'kb')
        assert kb['enabled'] is False

    def test_save_isolated_per_user(self, admin_client, viewer_client):
        r = admin_client.put('/api/system/sidebar', json={'groups': []})
        assert r.get_json()['code'] == 0
        r = viewer_client.get('/api/system/sidebar')
        groups = r.get_json()['data']
        assert all(g['enabled'] for g in groups)  # viewer 未保存，仍默认

    def test_reset(self, admin_client):
        admin_client.put('/api/system/sidebar', json={'groups': []})
        r = admin_client.post('/api/system/sidebar/reset')
        assert r.get_json()['code'] == 0
        r = admin_client.get('/api/system/sidebar')
        assert all(g['enabled'] for g in r.get_json()['data'])

    def test_invalid_payload(self, admin_client):
        r = admin_client.put('/api/system/sidebar', json={'groups': 'x'})
        assert r.status_code == 400
