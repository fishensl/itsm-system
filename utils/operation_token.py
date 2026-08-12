"""Default-off operation-token enforcement decorator."""
from functools import wraps

from flask import jsonify, request
from flask_login import current_user

from utils.settings import setting_bool
from utils.totp import verify_operation_token


def require_op_token(when=None):
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            if not setting_bool('op_code_enforce', False):
                return func(*args, **kwargs)
            if when is not None and not when():
                return func(*args, **kwargs)
            token = request.headers.get('X-Operation-Token', '')
            if not verify_operation_token(token, current_user.id,
                                          getattr(current_user, 'auth_version', 0)):
                return jsonify({'code': 1, 'message': '需要操作动态码验证'}), 403
            return func(*args, **kwargs)
        return wrapper
    return decorator
