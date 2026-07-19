# -*- coding: utf-8 -*-
"""pytest 全局夹具：临时 SQLite 库 + 四角色用户 + 测试客户端"""
import os
import sys
import tempfile

import pytest

# 项目根目录加入 sys.path（从 tests/ 子目录导入 app/models/...）
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.setdefault('ITSM_SECRET_KEY', 'test-secret-key-for-pytest')

from app import create_app  # noqa: E402
from models import db, User  # noqa: E402

TEST_PASSWORD = 'test123456'


@pytest.fixture(scope='module')
def app():
    """模块级应用实例（建库成本高，每模块一次）；用例间由 _fresh_db 清库隔离"""
    tmp = tempfile.mkdtemp(prefix='itsm_test_')
    db_uri = 'sqlite:///' + os.path.join(tmp, 'test.db').replace(os.sep, '/')
    application = create_app({
        'TESTING': True,
        'SECRET_KEY': 'test-secret-key-for-pytest',
        'SQLALCHEMY_DATABASE_URI': db_uri,
        'WTF_CSRF_ENABLED': False,   # 测试默认关 CSRF；CSRF 行为由专门用例覆盖
        'RATELIMIT_ENABLED': False,  # 限流不干扰测试
    })
    with application.app_context():
        db.create_all()
        _reseed()
    yield application
    with application.app_context():
        db.session.remove()
        db.drop_all()


@pytest.fixture(autouse=True)
def _fresh_db(app):
    """每个用例前清空全部表并重播种（SQLite 默认不强制 FK，删除顺序无关）"""
    with app.app_context():
        db.session.remove()
        for table in reversed(db.metadata.sorted_tables):
            db.session.execute(table.delete())
        db.session.commit()
        _reseed()
    yield


def _reseed():
    """权限/角色种子 + 四角色测试用户（幂等）"""
    from utils.seed_permissions import seed_all
    seed_all()
    _create_test_users()


def _create_test_users():
    """四角色测试用户：admin/op/sales/viewer，密码均为 TEST_PASSWORD"""
    for username, role in [('admin', 'admin'), ('op', 'operator'),
                           ('sales', 'sales'), ('viewer', 'viewer')]:
        if not User.query.filter_by(username=username).first():
            db.session.add(User.create_with_password(
                username=username, password=TEST_PASSWORD,
                realname=username, role=role))
    db.session.commit()


@pytest.fixture()
def client(app):
    return app.test_client()


def login(client, username, password=TEST_PASSWORD):
    """测试辅助：表单登录"""
    return client.post('/login', data={'username': username, 'password': password},
                       follow_redirects=False)


# 各角色客户端：独立 test_client（cookie jar 隔离，避免同测试内多角色登录互相覆盖）
@pytest.fixture()
def admin_client(app):
    c = app.test_client()
    login(c, 'admin')
    return c


@pytest.fixture()
def op_client(app):
    c = app.test_client()
    login(c, 'op')
    return c


@pytest.fixture()
def sales_client(app):
    c = app.test_client()
    login(c, 'sales')
    return c


@pytest.fixture()
def viewer_client(app):
    c = app.test_client()
    login(c, 'viewer')
    return c
