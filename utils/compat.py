"""兼容端点退役辅助：统一响应头与结构化访问日志。"""
from functools import wraps

from flask import current_app, make_response, request
from flask_login import current_user


def mark_deprecated(response, successor: str):
    """给兼容响应添加机器可读弃用信息，并记录调用方。"""
    wrapped = make_response(response)
    wrapped.headers['Deprecation'] = 'true'
    wrapped.headers['Link'] = f'<{successor}>; rel="successor-version"'
    user_id = current_user.get_id() if getattr(current_user, 'is_authenticated', False) else None
    current_app.logger.info(
        'compat_endpoint_access endpoint=%s method=%s path=%s user_id=%s remote_addr=%s successor=%s',
        request.endpoint, request.method, request.path, user_id, request.remote_addr, successor,
    )
    return wrapped


def deprecated_endpoint(successor: str):
    """装饰尚不能删除的兼容视图；successor 可以是路径或迁移说明。"""
    def decorator(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            return mark_deprecated(view(*args, **kwargs), successor)
        return wrapped
    return decorator
