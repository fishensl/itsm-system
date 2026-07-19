#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ITSM 简易运维管理系统 - 主应用"""

import json
import os

from flask import (Flask, render_template, request, redirect, url_for,
                   jsonify, current_app)
from flask_login import (LoginManager)
from flask_wtf.csrf import CSRFProtect, generate_csrf
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from werkzeug.middleware.proxy_fix import ProxyFix

from models import db, User, DeviceType, FaultType
from utils.permission import register_template_functions
from config import Config, setup_logging, setup_security_headers

# ==================== 扩展实例（应用工厂模式：在 create_app 中 init_app） ====================
csrf = CSRFProtect()
# Limiter：基于 IP 的限流（限流存储使用内存，单进程足够）
limiter = Limiter(
    key_func=get_remote_address,
    default_limits=[],  # 默认不限；个别路由显式声明
    headers_enabled=True,
)
login_manager = LoginManager()
login_manager.login_view = 'login'
# flask-migrate（Alembic）接管 schema 演进：替代旧 utils/seed_permissions.py 的 PRAGMA 自动 ADD COLUMN
# init_db() 内部会调 flask db upgrade 应用 migrations/ 下的迁移脚本
from flask_migrate import Migrate
migrate = Migrate()

# V13: 证书选项注入 Jinja 全局，模板按分组渲染 checkbox
from utils.cert_options import CERT_CATEGORIES as _CERT_CATEGORIES

# 读取应用版本号
_VERSION_FILE = os.path.join(os.path.dirname(__file__), 'VERSION')
try:
    with open(_VERSION_FILE, 'r', encoding='utf-8') as _vf:
        _APP_VERSION = _vf.read().strip()
except Exception:
    _APP_VERSION = 'unknown'


# CSRF token 同步写入非 HttpOnly cookie，供前端 JS 读取（create_app 中 after_request 注册）
def _set_csrf_cookie(response):
    try:
        # 触发 token 生成（写入 session + g.csrf_token）
        token = generate_csrf()
        response.set_cookie(
            'csrf_token', token,
            max_age=60 * 60 * 4,
            httponly=False,  # 允许 JS 读取以放进 X-CSRFToken 头
            samesite='Lax',
            secure=request.is_secure,  # 跟随真实请求协议：HTTPS 才带 Secure，LAN 走 HTTP 也能落地
        )
    except Exception:
        pass
    return response


# ==================== 全局错误处理（create_app 中 register_error_handler 注册） ====================
def err_404(e):
    return render_template('errors/error.html', code=404,
                           title='页面未找到', message='您访问的页面不存在或已被移除。',
                           show_back=True), 404


def err_500(e):
    current_app.logger.exception('500 错误: %s', e)
    return render_template('errors/error.html', code=500,
                           title='服务器内部错误', message='抱歉，服务器处理您的请求时出错。请稍后重试或联系管理员。',
                           show_back=True), 500


def err_403(e):
    return render_template('errors/error.html', code=403,
                           title='权限不足', message='您没有权限访问此页面。',
                           show_back=True), 403


def err_413(e):
    return render_template('errors/error.html', code=413,
                           title='文件过大', message='上传的文件超过系统允许的大小限制（默认 100MB）。',
                           show_back=True), 413


# 注入 csrf_token() 到所有模板（也可用 {{ csrf_token() }} 直接调用）
def inject_csrf_token():
    return {'csrf_token': generate_csrf}


# 注入侧栏配置到所有模板
def inject_sidebar():
    """每个请求渲染时，根据当前用户的偏好返回侧栏分组"""
    from utils.sidebar_config import get_user_sidebar_groups
    try:
        from flask_login import current_user
        if current_user.is_authenticated:
            groups = get_user_sidebar_groups(current_user)
        else:
            from utils.sidebar_config import get_default_groups
            groups = [
                {
                    'key': g['key'],
                    'title': g['title'],
                    'icon': g['icon'],
                    'enabled': True,
                    'single_link': g.get('single_link'),
                    'children': g.get('children', []),
                }
                for g in get_default_groups()
            ]
    except Exception:
        from utils.sidebar_config import get_default_groups
        groups = [
            {
                'key': g['key'],
                'title': g['title'],
                'icon': g['icon'],
                'enabled': True,
                'single_link': g.get('single_link'),
                'children': g.get('children', []),
            }
            for g in get_default_groups()
        ]
    return {'sidebar_groups': groups, 'request_path': request.path}


def from_json_filter(value):
    try:
        return json.loads(value) if value else []
    except:
        return []


@login_manager.user_loader
def load_user(user_id):
    # 仅加载启用账号：停用用户的现有 session 立即失效
    return User.query.filter_by(id=int(user_id), is_active=True).first()



# ==================== 路由集中注册 ====================
def register_routes(app):
    """集中注册主应用路由（视图函数在 views/ 包，端点名与历史完全一致）。"""
    from views import dashboard, auth, admin_users, system

    app.add_url_rule('/', 'index', dashboard.index)
    app.add_url_rule('/login', 'login', auth.login, methods=['GET', 'POST'])
    app.add_url_rule('/logout', 'logout', auth.logout)
    app.add_url_rule('/system/repair-schema', 'repair_schema', system.repair_schema)
    app.add_url_rule('/system/drawio-diag', 'drawio_diag', system.drawio_diag)
    app.add_url_rule('/users', 'user_list', admin_users.user_list, methods=['GET', 'POST'])
    app.add_url_rule('/users/delete/<int:id>', 'user_delete', admin_users.user_delete, methods=['POST'])
    app.add_url_rule('/users/add', 'user_add', admin_users.user_add, methods=['POST'])
    app.add_url_rule('/users/edit/<int:id>', 'user_edit', admin_users.user_edit, methods=['GET', 'POST'])
    app.add_url_rule('/users/<int:id>/reset_password', 'user_reset_password',
                     admin_users.user_reset_password, methods=['POST'])
    app.add_url_rule('/me/change_password', 'me_change_password', auth.me_change_password,
                     methods=['GET', 'POST'])
    app.add_url_rule('/system', 'system_settings', system.system_settings)
    app.add_url_rule('/system/sidebar', 'system_sidebar', system.system_sidebar, methods=['GET', 'POST'])
    app.add_url_rule('/api/sidebar/reset', 'api_sidebar_reset', system.api_sidebar_reset, methods=['POST'])
    app.add_url_rule('/permissions', 'permission_list', admin_users.permission_list)
    app.add_url_rule('/ai-config', 'ai_config_page', admin_users.ai_config_page, methods=['GET', 'POST'])
    app.add_url_rule('/ai-config/delete/<int:id>', 'ai_config_delete', admin_users.ai_config_delete,
                     methods=['POST'])
    app.add_url_rule('/dashboard/reports', 'dashboard_reports', system.dashboard_reports)
    app.add_url_rule('/exports/download-template/<module>', 'download_template', system.download_template)
    app.add_url_rule('/customers', 'customer_list', system.customer_list)
    app.add_url_rule('/api/dashboard/opportunity-stages', 'api_dashboard_opp_stages',
                     dashboard.api_dashboard_opp_stages)
    app.add_url_rule('/api/dashboard/preferences', 'api_dashboard_preferences',
                     dashboard.api_dashboard_preferences)
    app.add_url_rule('/api/dashboard/preferences', 'api_dashboard_preferences_save',
                     dashboard.api_dashboard_preferences_save, methods=['POST'])
    app.add_url_rule('/api/dashboard/preferences/reset', 'api_dashboard_preferences_reset',
                     dashboard.api_dashboard_preferences_reset, methods=['POST'])


# ==================== 运行时目录 ====================
def _ensure_runtime_dirs():
    """创建运行时目录（替代原各蓝图模块级 os.makedirs 导入副作用）"""
    base = os.path.dirname(os.path.abspath(__file__))
    for d in ('instance', 'logs', 'reports', 'uploads', 'backups',
              os.path.join('static', 'uploads'),
              os.path.join('static', 'uploads', 'spare_parts'),
              os.path.join('static', 'uploads', 'knowledge')):
        os.makedirs(os.path.join(base, d), exist_ok=True)


# ==================== 应用工厂 ====================
def create_app(test_config=None):
    """应用工厂：创建并配置 Flask 实例。

    test_config: 测试/特殊部署时的配置覆盖 dict
    （如 SQLALCHEMY_DATABASE_URI 指向临时库、WTF_CSRF_ENABLED=False、RATELIMIT_ENABLED=False）。
    """
    _ensure_runtime_dirs()
    app = Flask(__name__)
    # 经 nginx/反代时识别 X-Forwarded-Proto，使 request.is_secure 正确反映外部协议
    app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1)
    app.config['SECRET_KEY'] = Config.SECRET_KEY
    app.config['SQLALCHEMY_DATABASE_URI'] = Config.SQLALCHEMY_DATABASE_URI
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = Config.SQLALCHEMY_TRACK_MODIFICATIONS
    app.config['MAX_CONTENT_LENGTH'] = Config.MAX_CONTENT_LENGTH
    # CSRF：默认对所有 POST/PUT/PATCH/DELETE 启用
    app.config['WTF_CSRF_HEADERS'] = ['X-CSRFToken', 'X-CSRF-Token']
    app.config['WTF_CSRF_TIME_LIMIT'] = 60 * 60 * 4  # 4 小时
    # Limiter：基于 IP 的限流（限流存储使用内存，单进程足够）
    app.config['RATELIMIT_STORAGE_URI'] = 'memory://'
    if test_config:
        app.config.update(test_config)

    setup_logging(app)
    register_template_functions(app)
    setup_security_headers(app)

    # V13: 证书选项注入 Jinja 全局，模板按分组渲染 checkbox
    app.jinja_env.globals['CERT_CATEGORIES'] = _CERT_CATEGORIES
    app.jinja_env.globals['APP_VERSION'] = _APP_VERSION

    # CSRF 必须在 register_blueprints 之前 init（login 路由已通过 @csrf.exempt 豁免）
    csrf.init_app(app)
    # CSRF token 同步写入非 HttpOnly cookie，供前端 JS 读取
    app.after_request(_set_csrf_cookie)

    db.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)
    limiter.init_app(app)

    # API 请求未登录返回 JSON 401（而非 302 跳登录页，避免前端 fetch 解析到 HTML）
    # 判定同 utils.permission._is_api_request：兼容蓝图内 /xxx/api/... 路径
    @login_manager.unauthorized_handler
    def _unauthorized():
        if '/api/' in request.path:
            return jsonify({'success': False, 'error': '未登录或会话已过期'}), 401
        return redirect(url_for('login', next=request.url))

    # 全局错误处理
    app.register_error_handler(404, err_404)
    app.register_error_handler(500, err_500)
    app.register_error_handler(403, err_403)
    app.register_error_handler(413, err_413)

    # 上下文处理器 / 模板过滤器
    app.context_processor(inject_csrf_token)
    app.context_processor(inject_sidebar)
    app.add_template_filter(from_json_filter, 'from_json')

    # 主应用路由（必须先于蓝图注册，与原模块级定义顺序一致）
    register_routes(app)

    # 注册业务蓝图模块
    from blueprints import register_blueprints
    register_blueprints(app)

    return app


# ---------- 初始化 ----------
def _bootstrap_legacy_db(app):
    """引导遗留库（由旧 db.create_all + ensure_schema 建好但无 alembic_version）接入 Alembic。

    三种库状态：
      1) 空库：无任何业务表 → 不处理，交给 flask db upgrade 从零建表。
      2) 遗留库：有业务表但无 alembic_version 表 → 其 schema 与 initial_schema 一致
         （interface=VARCHAR(128)、customers.name/tickets.number 无唯一约束），
         故 stamp 到 initial_schema，后续 upgrade 只跑 pg_type_fixes。
      3) 已接入 Alembic：有 alembic_version → 不处理，交给 upgrade。
    返回 True 表示已处理（调用了 stamp），False 表示无需处理。
    """
    from sqlalchemy import inspect as sqla_inspect
    insp = sqla_inspect(db.engine)
    all_tables = set(insp.get_table_names())
    if 'alembic_version' in all_tables:
        return False  # 已接入
    business_tables = all_tables - {'alembic_version', 'sqlite_sequence'}
    if not business_tables:
        return False  # 空库，让 upgrade 从零建

    # 遗留库：有业务表但无 alembic_version。先清理可能阻塞 pg_type_fixes 唯一约束的重复数据。
    _dedup_before_unique_constraints()

    # stamp 到 initial_schema（遗留库结构与 initial_schema 一致），之后 upgrade 只需跑 pg_type_fixes
    from flask_migrate import stamp as _migrate_stamp
    import os as _os
    _migrate_stamp(directory=_os.path.join(_os.path.dirname(__file__), 'migrations'),
                   revision='3f82f965fb25')
    app.logger.info('检测到遗留库（无 alembic_version），已 stamp 到 initial_schema，后续 upgrade 将应用 pg_type_fixes')
    return True


def _dedup_before_unique_constraints():
    """给即将加唯一约束的列清理重复行（保留 id 最小者，其余改名加后缀使其唯一）。

    - customers.name：重名客户给较新者追加 " (重复N)" 后缀
    - tickets.number：重号工单给较新者追加 "-DUP-N" 后缀
    幂等：已是唯一则无操作。失败仅告警不中断（不阻塞启动）。
    """
    from sqlalchemy import text
    try:
        # customers.name
        dup_names = db.session.execute(text(
            "SELECT name, COUNT(*) c FROM customers GROUP BY name HAVING COUNT(*) > 1"
        )).all()
        for name, _cnt in dup_names:
            rows = db.session.execute(text(
                "SELECT id FROM customers WHERE name = :n ORDER BY id"
            ), {'n': name}).all()
            for i, (cid,) in enumerate(rows[1:], start=1):
                new_name = f'{name} (重复{i})'
                # 截断到 128 字符以符合 String(128)
                if len(new_name) > 128:
                    new_name = new_name[:128]
                db.session.execute(text(
                    "UPDATE customers SET name = :nn WHERE id = :id"
                ), {'nn': new_name, 'id': cid})
        # tickets.number
        dup_nums = db.session.execute(text(
            "SELECT number, COUNT(*) c FROM tickets GROUP BY number HAVING COUNT(*) > 1"
        )).all()
        for num, _cnt in dup_nums:
            rows = db.session.execute(text(
                "SELECT id FROM tickets WHERE number = :n ORDER BY id"
            ), {'n': num}).all()
            for i, (tid,) in enumerate(rows[1:], start=1):
                new_num = f'{num}-DUP{i}'
                if len(new_num) > 32:
                    new_num = (num[:32 - len(f'-DUP{i}')] + f'-DUP{i}')
                db.session.execute(text(
                    "UPDATE tickets SET number = :nn WHERE id = :id"
                ), {'nn': new_num, 'id': tid})
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        app.logger.warning('去重清理失败（非致命，可能在 pg_type_fixes 加唯一约束时报错）: %s', e)


def init_db(app):
    """初始化数据库：Alembic 迁移 + 种子数据 + 默认账号（幂等）。"""
    with app.app_context():
        # Schema 演进交给 Alembic（flask-migrate），替代旧 db.create_all + ensure_schema(PRGAMA)
        from flask_migrate import upgrade as _migrate_upgrade
        import os as _os
        migrations_dir = _os.path.join(_os.path.dirname(__file__), 'migrations')

        # 先引导遗留库（有表但无 alembic_version 的旧 SQLite 库）接入 Alembic
        _bootstrap_legacy_db(app)

        # 应用所有待执行的迁移（空库会从 initial_schema 一路建到 head；遗留库只跑 pg_type_fixes）
        _migrate_upgrade(directory=migrations_dir)

        # V14: 权限/角色 seed（幂等，仅写数据不改 schema）
        try:
            from utils.seed_permissions import seed_all
            seed_all(app)
        except Exception as e:
            app.logger.warning('权限 seed 失败（非致命）: %s', e)
            db.session.rollback()

        # 创建默认管理员：仅在系统中不存在任何 admin 角色用户时（首次空库引导），
        # 避免管理员把 admin 改名/删除后，重启又重建 admin/admin123 弱口令后门
        if User.query.filter_by(role='admin').count() == 0:
            admin = User.create_with_password(username='admin', password='admin123', realname='管理员', role='admin')
            db.session.add(admin)
            db.session.commit()
            app.logger.info('默认管理员已创建: admin / admin123')

        # 创建默认设备类型
        if DeviceType.query.count() == 0:
            defaults = ['路由器', '交换机', '防火墙', '服务器', '负载均衡', '无线AP', '光传输', 'UPS电源', '空调', '其他']
            for i, name in enumerate(defaults):
                db.session.add(DeviceType(name=name, sort_order=i))
            db.session.commit()
            app.logger.info('默认设备类型已创建')

        # 创建默认故障类型
        if FaultType.query.count() == 0:
            defaults = ['网络中断', '设备故障', '安全事件', '链路故障', '电源故障', '配置错误', '性能问题', '其他']
            for i, name in enumerate(defaults):
                db.session.add(FaultType(name=name, sort_order=i))
            db.session.commit()
            app.logger.info('默认故障类型已创建')


if __name__ == '__main__':
    app = create_app()
    init_db(app)
    app.logger.info('=' * 50)
    app.logger.info('=== ITSM 简易运维管理系统 ===')
    app.logger.info('=' * 50)
    app.logger.info('默认登录: admin / admin123')
    app.logger.info('访问地址: http://127.0.0.1:5000')
    app.logger.info('=' * 50)
    app.run(debug=True, host='127.0.0.1', port=5000)
