"""操作令牌守卫；全局可选，指定敏感操作在外网强制执行。"""
from functools import wraps

from flask import jsonify, request
from flask_login import current_user

from utils.settings import setting_bool
from utils.totp import verify_operation_token


def require_op_token(when=None, *, external_required=False):
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            from utils.access_control import is_internal_request
            force_external = external_required and not is_internal_request()
            if not force_external and not setting_bool('op_code_enforce', False):
                return func(*args, **kwargs)
            if force_external and not current_user.mfa_enabled:
                return jsonify({'code': 1, 'message': '尚未绑定账号 MFA，请先在修改密码中完成绑定'}), 403
            if when is not None and not when():
                return func(*args, **kwargs)
            token = request.headers.get('X-Operation-Token', '')
            if not verify_operation_token(token, current_user.id,
                                          getattr(current_user, 'auth_version', 0)):
                return jsonify({'code': 1, 'message': '需要操作动态码验证'}), 403
            return func(*args, **kwargs)
        return wrapper
    return decorator
