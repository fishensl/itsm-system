"""Restrict accounts with temporary passwords to the recovery surface."""
from flask import jsonify, request
from flask_login import current_user


_ALLOWED_EXACT = {
    '/api/auth/me',
    '/api/auth/change-password',
    '/api/auth/logout',
    '/api/auth/security-profile',
}
_ALLOWED_PAGE_EXACT = {'/', '/login', '/logout', '/favicon.ico'}
_ALLOWED_PAGE_PREFIXES = ('/app', '/static/')


def register_password_change_guard(app):
    @app.before_request
    def _require_password_change():
        if not current_user.is_authenticated or not current_user.must_change_password:
            return None
        path = request.path.rstrip('/') or '/'
        if path in _ALLOWED_PAGE_EXACT or path.startswith(_ALLOWED_PAGE_PREFIXES):
            return None
        if path in _ALLOWED_EXACT or path.startswith('/api/auth/mfa/'):
            return None
        return jsonify({
            'code': 1,
            'data': None,
            'message': '当前密码为临时密码，请先修改密码',
        }), 403
