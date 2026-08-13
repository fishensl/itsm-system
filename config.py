"""应用配置"""
import os
import logging
import secrets

BASE_DIR = os.path.abspath(os.path.dirname(__file__))


class Config:
    """基础配置"""
    # P0-1.4: SECRET_KEY 必须显式配置；生产环境未设置则报错退出
    # 开发环境允许使用一个固定的 key（警告级别），但生产环境必须设环境变量
    SECRET_KEY = os.environ.get('ITSM_SECRET_KEY')
    if not SECRET_KEY:
        if os.environ.get('FLASK_ENV') == 'production' or os.environ.get('ITSM_ENV') == 'production':
            raise RuntimeError(
                '[FATAL] ITSM_SECRET_KEY 未配置。生产环境必须设置强随机密钥。\n'
                '建议：`python -c "import secrets; print(secrets.token_hex(32))"` 生成，'
                '然后 `export ITSM_SECRET_KEY=...`'
            )
        import warnings
        warnings.warn(
            '[SECURITY] 正在使用临时随机生成的 SECRET_KEY。重启后所有 session 将失效。\n'
            '生产部署前请设置环境变量 ITSM_SECRET_KEY。',
            RuntimeWarning,
            stacklevel=2,
        )
        SECRET_KEY = secrets.token_hex(32)

    # PG-only：主数据库为 PostgreSQL（SQLite 仅限测试/遗留迁移工具显式传入，
    # 不再默认回落）。生产未配置 ITSM_DATABASE_URI 直接拒绝启动。
    SQLALCHEMY_DATABASE_URI = os.environ.get('ITSM_DATABASE_URI')
    if not SQLALCHEMY_DATABASE_URI:
        if os.environ.get('FLASK_ENV') == 'production' or os.environ.get('ITSM_ENV') == 'production':
            raise RuntimeError(
                '[FATAL] ITSM_DATABASE_URI 未配置。生产环境必须设置 PostgreSQL 连接串。\n'
                '示例：`export ITSM_DATABASE_URI=postgresql://itsm:密码@localhost:5432/itsm`\n'
                '（SQLite 已不再作为默认，历史 SQLite 库请用 scripts/pg-migrate.sh 迁移到 PG）'
            )
        # 非生产（开发/测试）：显式 sqlite 仍可用（conftest 传入），缺省时给 PostgreSQL 提示
        import warnings
        warnings.warn(
            '[CONFIG] 未设置 ITSM_DATABASE_URI。开发环境请配置 PostgreSQL：\n'
            '  export ITSM_DATABASE_URI=postgresql://itsm:密码@localhost:5432/itsm\n'
            '测试/迁移工具可显式传 sqlite:/// 路径（如 pytest conftest）。',
            RuntimeWarning,
            stacklevel=2,
        )
        SQLALCHEMY_DATABASE_URI = 'sqlite:///' + os.path.join(BASE_DIR, 'instance', 'itsm.db')
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    MAX_CONTENT_LENGTH = int(os.environ.get('ITSM_MAX_UPLOAD_MB', 100)) * 1024 * 1024
    FORCE_HTTPS = os.environ.get('ITSM_FORCE_HTTPS', '').strip().lower() in {'1', 'true', 'yes', 'on'}
    IS_PRODUCTION = (os.environ.get('ITSM_ENV') == 'production' or
                     os.environ.get('FLASK_ENV') == 'production')
    MFA_ENFORCE = os.environ.get('ITSM_MFA_ENFORCE', '').strip().lower() in {'1', 'true', 'yes', 'on'}
    CSP_ENABLED = os.environ.get('ITSM_CSP_ENABLED', '').strip().lower() in {'1', 'true', 'yes', 'on'}
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'
    SESSION_COOKIE_SECURE = FORCE_HTTPS

    # 分页
    ITEMS_PER_PAGE = 20

    # 日志
    LOG_DIR = os.path.join(BASE_DIR, 'logs')
    LOG_FILE = os.path.join(LOG_DIR, 'app.log')
    LOG_LEVEL = logging.INFO


def setup_logging(app):
    """Use stdout/journald in production; keep a rotating file for local development."""
    if app.config.get('IS_PRODUCTION'):
        handler = logging.StreamHandler()
    else:
        from logging.handlers import RotatingFileHandler
        os.makedirs(Config.LOG_DIR, exist_ok=True)
        handler = RotatingFileHandler(
            Config.LOG_FILE, maxBytes=10 * 1024 * 1024, backupCount=10, encoding='utf-8')
    handler.setFormatter(logging.Formatter(
        '[%(asctime)s] %(levelname)s %(module)s:%(lineno)d - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    ))
    handler.setLevel(Config.LOG_LEVEL)
    app.logger.addHandler(handler)
    app.logger.setLevel(Config.LOG_LEVEL)
    app.logger.info('ITSM 应用启动')


def setup_security_headers(app):
    """注册安全头响应中间件"""
    from flask import request
    @app.after_request
    def add_security_headers(response):
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['X-Frame-Options'] = 'SAMEORIGIN'
        response.headers['X-XSS-Protection'] = '1; mode=block'
        response.headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains'
        if app.config.get('CSP_ENABLED'):
            response.headers['Content-Security-Policy'] = (
                "default-src 'self'; img-src 'self' data: blob:; style-src 'self' 'unsafe-inline'; "
                "script-src 'self'; connect-src 'self'; font-src 'self' data:; "
                "object-src 'none'; base-uri 'self'; frame-ancestors 'self'"
            )
        # drawio vendor(~21MB JS)与图标库内容不变，开长期 immutable 缓存；
        # 其余（动态接口、HTML 入口）保持 no-store，避免拿到过期数据
        p = request.path
        if p.startswith('/static/vendor/') or p.startswith('/static/stencils/'):
            response.headers['Cache-Control'] = 'public, max-age=31536000, immutable'
        elif (p.startswith('/api/') or p.startswith('/exports/') or
              p.startswith('/uploads/')):
            response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate'
            response.headers['Pragma'] = 'no-cache'
            response.headers['Expires'] = '0'
        else:
            response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate'
            response.headers['Pragma'] = 'no-cache'
            response.headers['Expires'] = '0'
        return response
