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

    SQLALCHEMY_DATABASE_URI = os.environ.get('ITSM_DATABASE_URI', f'sqlite:///{os.path.join(BASE_DIR, "instance", "itsm.db")}')
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    MAX_CONTENT_LENGTH = int(os.environ.get('ITSM_MAX_UPLOAD_MB', 100)) * 1024 * 1024

    # 分页
    ITEMS_PER_PAGE = 20

    # 日志
    LOG_DIR = os.path.join(BASE_DIR, 'logs')
    LOG_FILE = os.path.join(LOG_DIR, 'app.log')
    LOG_LEVEL = logging.INFO


def setup_logging(app):
    """配置日志"""
    os.makedirs(Config.LOG_DIR, exist_ok=True)
    handler = logging.FileHandler(Config.LOG_FILE, encoding='utf-8')
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
        # drawio vendor(~21MB JS)与图标库内容不变，开长期 immutable 缓存；
        # 其余（动态接口、HTML 入口）保持 no-store，避免拿到过期数据
        p = request.path
        if p.startswith('/static/vendor/') or p.startswith('/static/stencils/'):
            response.headers['Cache-Control'] = 'public, max-age=31536000, immutable'
        else:
            response.headers['Cache-Control'] = 'no-store, max-age=0'
        return response
