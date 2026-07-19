# -*- coding: utf-8 -*-
"""T0 工厂化冒烟：应用可创建、核心路由可达、未授权 API 返回 JSON 401"""
from tests.conftest import login


def test_login_page(client):
    assert client.get('/login').status_code == 200


def test_login_logout_flow(client):
    r = login(client, 'admin')
    assert r.status_code == 302
    assert client.get('/').status_code == 200
    client.get('/logout')
    assert client.get('/').status_code == 302


def test_wrong_password(client):
    r = client.post('/login', data={'username': 'admin', 'password': 'bad'})
    assert r.status_code == 200  # 重渲染登录页
    assert client.get('/').status_code == 302  # 未建立会话


def test_api_unauthorized_json_401(client):
    r = client.get('/api/dashboard/preferences')
    assert r.status_code == 401
    assert r.is_json


def test_page_unauthorized_redirects_to_login(client):
    r = client.get('/system')
    assert r.status_code == 302
    assert '/login' in r.headers.get('Location', '')


def test_index_ok_for_admin(admin_client):
    assert admin_client.get('/').status_code == 200


def test_404_page(admin_client):
    assert admin_client.get('/no-such-page').status_code == 404


def test_url_map_core_endpoints(app):
    """端点名保持历史兼容（模板 url_for 依赖）"""
    endpoints = {r.endpoint for r in app.url_map.iter_rules()}
    for ep in ('index', 'login', 'logout', 'user_list', 'user_edit',
               'system_settings', 'customer_list', 'permission_list',
               'ai_config_page', 'download_template'):
        assert ep in endpoints, f'端点缺失: {ep}'
