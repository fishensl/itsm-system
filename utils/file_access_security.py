"""Protect file entry points without expanding the external network allowlist."""
import os
import posixpath

from flask import abort, jsonify, request
from flask_login import current_user

from utils.access_control import is_internal_request
from utils.session_security import credential_session_context


def require_submission_access(version):
    from models import Inspection, Ticket
    from utils.permission import apply_scope_filter
    model = {'inspection': Inspection, 'ticket': Ticket}.get(version.entity_type)
    if model is None:
        abort(404)
    entity = model.query.get_or_404(version.entity_id)
    if not apply_scope_filter(model.query, model, current_user).filter(model.id == entity.id).first():
        abort(404)


def register_file_access_security(app):
    @app.before_request
    def enforce_file_access():
        path = '/' + posixpath.normpath(request.path.replace('\\', '/')).lstrip('/')
        # Business documents must use their authenticated, permission-checked routes.
        # Only existing ticket progress pictures retain a static compatibility URL.
        if path.startswith(('/static/uploads/', '/uploads/')):
            if not current_user.is_authenticated:
                abort(404)
            from models import Ticket
            from utils.customer_scope import require_customer_access
            parts = path.split('/')
            if len(parts) != 6 or not parts[4].isdigit():
                abort(404)
            ticket = Ticket.query.get_or_404(int(parts[4]))
            require_customer_access(current_user, ticket.customer_id)
            from utils.permission import has_permission
            from utils.upload import ALLOWED_IMAGE_EXT
            if (not path.startswith('/static/uploads/ticket_progress/') or
                    os.path.splitext(path)[1].lower() not in ALLOWED_IMAGE_EXT or
                    not has_permission('ticket:view')):
                abort(404)
        if not current_user.is_authenticated:
            return None  # The route's login_required still rejects pending/expired sessions.
        # Import templates are explicitly exempt; they retain module permissions.
        if request.endpoint == 'download_template':
            return None
        sensitive = (
            path.startswith(('/static/uploads/', '/uploads/')) or
            (request.method in ('GET', 'HEAD') and any(
                part in path for part in ('/report/', '/reports/', '/download', '/preview',
                                          '/config-backup/', '/assets/'))) or
            any(part in path for part in ('/reveal-password', '/export-password', '/export-unlock'))
        )
        if sensitive:
            try:
                external = not is_internal_request()
            except Exception:
                external = True
            if external and not credential_session_context(current_user):
                return jsonify({'code': 1, 'message': '外网访问敏感文件或密码需要完成 MFA 登录验证'}), 403
        return None

    @app.after_request
    def protect_file_response(response):
        if ('Content-Disposition' in response.headers or
                request.path.startswith(('/static/uploads/', '/uploads/'))):
            response.headers['X-Content-Type-Options'] = 'nosniff'
            response.headers['Cache-Control'] = 'no-store'
            response.headers['Content-Security-Policy'] = "sandbox; default-src 'none'"
        return response
