# -*- coding: utf-8 -*-
"""T0 工厂化冒烟：应用可创建、核心路由可达、未授权 API 返回 JSON 401"""
from tests.conftest import login


def test_login_page(client):
    # SSR 业务页已剥离：GET 登录页一律重定向到 SPA 登录页
    r = client.get('/login')
    assert r.status_code == 302
    assert '/app/login' in r.headers.get('Location', '')


def test_login_logout_flow(client):
    r = login(client, 'admin')
    assert r.status_code == 302
    # 首页重定向到 /app/
    r = client.get('/')
    assert r.status_code == 302
    assert r.headers.get('Location', '').endswith('/app/')
    client.get('/logout')
    assert client.get('/').status_code == 302


def test_wrong_password(client):
    r = client.post('/login', data={'username': 'admin', 'password': 'bad'})
    assert r.status_code == 302  # 登录失败不再渲染，重定向 SPA 登录页
    assert '/app/login' in r.headers.get('Location', '')
    assert client.get('/').status_code == 302  # 未建立会话


def test_api_unauthorized_json_401(client):
    r = client.get('/api/dashboard/preferences')
    assert r.status_code == 401
    assert r.is_json


def test_page_unauthorized_redirects_to_login(client):
    r = client.get('/system/repair-schema')
    assert r.status_code == 302
    assert '/login' in r.headers.get('Location', '')


def test_index_ok_for_admin(admin_client):
    """已登录首页 302 → /app/"""
    r = admin_client.get('/')
    assert r.status_code == 302
    assert r.headers.get('Location', '').endswith('/app/')


def test_404_page(admin_client):
    assert admin_client.get('/no-such-page').status_code == 404


def test_url_map_core_endpoints(app):
    """保留端点名（SSR 业务端点已剥离）"""
    endpoints = {r.endpoint for r in app.url_map.iter_rules()}
    for ep in ('index', 'login', 'logout', 'repair_schema', 'drawio_diag',
               'download_template', 'api_sidebar_reset'):
        assert ep in endpoints, f'端点缺失: {ep}'


def test_device_list_page_gone(admin_client):
    """回归：SSR 设备列表页已剥离（Vue /app/devices 接管）"""
    r = admin_client.get('/devices')
    assert r.status_code == 404
