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


# ---- Flask-Login g._login_user 跨请求缓存兼容补丁（测试环境专用） ----
# Flask 3.1 下 g 绑定 contextvar，test_client 在同一线程顺序发起多请求时，
# g 可能跨请求残留（表现为 A client 的请求读到 B client 的用户身份）。
# 生产环境每个请求独立线程不受影响。此处禁用 _get_user 的缓存短路：
# 每个请求都强制走 login_manager._load_user()（按 session 重新加载用户）。
import flask_login.utils as _fl_utils  # noqa: E402
from flask import g as _fl_g  # noqa: E402
from flask import has_request_context as _has_req_ctx  # noqa: E402


def _get_user_no_cache():
    if _has_req_ctx():
        if '_login_user' not in _fl_g:
            from flask import current_app
            current_app.login_manager._load_user()
        # 若 g 残留了旧用户（跨请求），强制按 session 重载
        elif _fl_g.get('_login_user') is not None:
            from flask import current_app
            current_app.login_manager._load_user()
        return _fl_g.get('_login_user')
    return None


_fl_utils._get_user = _get_user_no_cache


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
    """四角色测试用户：admin/op/sales/viewer，密码均为 TEST_PASSWORD

    op 用户级 grant inspection:review / ticket:review：V24 起 operator 角色不再下发审核
    权限（审核岗位 = admin + 用户级授权），op 保留审核能力以对齐既有审核用例。
    """
    from models import UserPermission
    for username, role in [('admin', 'admin'), ('op', 'operator'),
                           ('sales', 'sales'), ('viewer', 'viewer')]:
        if not User.query.filter_by(username=username).first():
            db.session.add(User.create_with_password(
                username=username, password=TEST_PASSWORD,
                realname=username, role=role))
    db.session.flush()
    op = User.query.filter_by(username='op').first()
    for perm_code in ('inspection:review', 'ticket:review'):
        exists = UserPermission.query.filter_by(user_id=op.id, permission_code=perm_code).first()
        if not exists:
            db.session.add(UserPermission(user_id=op.id, permission_code=perm_code,
                                          grant_type='grant'))
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


@pytest.fixture()
def report_dirs(tmp_path, monkeypatch):
    """报告中心磁盘目录隔离：reports/ 与 static/uploads 指向临时目录，避免读到真实运行时文件"""
    from blueprints import vue_api_ops as _ops
    rdir = tmp_path / 'reports'
    udir = tmp_path / 'uploads'
    rdir.mkdir(parents=True, exist_ok=True)
    udir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(_ops, 'REPORTS_DIR', str(rdir))
    monkeypatch.setattr(_ops, 'UPLOADS_DIR', str(udir))
    return {'reports': str(rdir), 'uploads': str(udir)}
