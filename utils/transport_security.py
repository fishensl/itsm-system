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


def _is_device_credential_request() -> bool:
    """仅设备凭据设置/查看允许走可信内网 HTTP 兼容通道。"""
    return '/reveal-password' in request.path or _contains_password_write()


def register_transport_security(app):
    """Reject credential-bearing HTTP in production.

    设备管理接口兼容已配置的可信内网/VPN：外网 HTTP 仍拒绝；用户改密、
    管理员重置、密码导出等其他高风险操作仍必须使用 HTTPS。
    """
    @app.before_request
    def require_https_for_credentials():
        if request.is_secure or app.testing:
            return None
        production = bool(app.config.get('IS_PRODUCTION'))
        if not (app.config.get('FORCE_HTTPS') or production):
            return None
        if _is_sensitive_request():
            if _is_device_credential_request():
                try:
                    from utils.access_control import is_internal_request
                    if is_internal_request():
                        return None
                except Exception:
                    app.logger.exception('设备凭据传输可信网段判定失败')
            return jsonify({'code': 1, 'message': '该敏感操作必须通过 HTTPS 访问'}), 403
        return None
