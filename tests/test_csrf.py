# -*- coding: utf-8 -*-
"""W0-S6 CSRF 策略验证：取消蓝图级豁免后，JSON API 仍受 CSRF 保护。

本模块使用独立 app 实例（WTF_CSRF_ENABLED=True），与全局 conftest 的默认关闭相反。
"""
import os
import tempfile

import pytest

from app import create_app
from models import db


@pytest.fixture()
def csrf_app():
    tmp = tempfile.mkdtemp(prefix='itsm_csrf_')
    application = create_app({
        'TESTING': True,
        'SECRET_KEY': 'csrf-test-secret',
        'SQLALCHEMY_DATABASE_URI': 'sqlite:///' + os.path.join(tmp, 't.db').replace(os.sep, '/'),
        'WTF_CSRF_ENABLED': True,
        'RATELIMIT_ENABLED': False,
    })
    with application.app_context():
        db.create_all()
        from utils.seed_permissions import seed_all
        from models import User
        seed_all()
        db.session.add(User.create_with_password(
            username='op', password='test123456', realname='op', role='operator'))
        db.session.commit()
    yield application


@pytest.fixture()
def csrf_client(csrf_app):
    c = csrf_app.test_client()
    c.post('/login', data={'username': 'op', 'password': 'test123456'})  # login 豁免 CSRF
    return c


def _csrf_token(client):
    cookie = client.get_cookie('csrf_token')
    return cookie.value if cookie else ''


class TestCsrfProtection:
    def test_draft_save_without_token_rejected(self, csrf_client):
        """取消蓝图豁免后：无 X-CSRFToken 的 POST 被 400 拒绝"""
        r = csrf_client.post('/api/drafts/save', json={
            'form_type': 'ticket', 'related_id': 1, 'form_data_json': {}})
        assert r.status_code == 400

    def test_draft_save_with_token_accepted(self, csrf_client):
        csrf_client.get('/')  # 触发 csrf cookie 写入
        token = _csrf_token(csrf_client)
        assert token
        r = csrf_client.post('/api/drafts/save',
                             json={'form_type': 'ticket', 'related_id': 1, 'form_data_json': {}},
                             headers={'X-CSRFToken': token})
        assert r.status_code == 200

    def test_rack_api_without_token_rejected(self, csrf_client):
        """rack 蓝图豁免已移除：POST 无机柜令牌 → 400"""
        r = csrf_client.post('/api/rack/cabinets', json={'name': 'A01', 'customer_id': 1})
        assert r.status_code == 400

    def test_get_requests_unaffected(self, csrf_client):
        """GET 不受 CSRF 约束"""
        assert csrf_client.get('/api/rack/cabinets').status_code == 200
        assert csrf_client.get('/api/drafts/list').status_code == 200

    def test_login_exempt_still_works(self, csrf_app):
        c = csrf_app.test_client()
        r = c.post('/login', data={'username': 'op', 'password': 'test123456'})
        assert r.status_code == 302  # 未带 token 也能登录（登录页豁免）
