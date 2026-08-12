"""Transport guard for operations that can carry plaintext credentials."""
from flask import jsonify, request


_SENSITIVE_PATH_PARTS = (
    '/reveal-password',
    '/export-password-request',
    '/export-password-reviews/',
    '/change-password',
    '/reset-password',
    '/offboard',
    '/op-verify',
)


def _contains_password_write() -> bool:
    if request.method not in {'POST', 'PUT', 'PATCH'}:
        return False
    if '/api/devices' not in request.path:
        return False
    payload = request.get_json(silent=True)
    if isinstance(payload, dict) and 'password' in payload:
        return True
    return 'password' in request.form


def _is_sensitive_request() -> bool:
    path = request.path
    return any(part in path for part in _SENSITIVE_PATH_PARTS) or _contains_password_write()


def register_transport_security(app):
    """Reject credential-bearing HTTP in production; tests and development stay compatible."""
    @app.before_request
    def require_https_for_credentials():
        if request.is_secure or app.testing:
            return None
        production = bool(app.config.get('IS_PRODUCTION'))
        if not (app.config.get('FORCE_HTTPS') or production):
            return None
        if _is_sensitive_request():
            return jsonify({'code': 1, 'message': '该敏感操作必须通过 HTTPS 访问'}), 403
        return None
