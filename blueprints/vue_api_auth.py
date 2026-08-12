"""Default-off MFA, operation verification and security profile APIs."""
from datetime import datetime
from functools import wraps

from flask import g, request, session
from flask_login import current_user, login_required, login_user

from blueprints.vue_api import _user_payload, fail, ok, vue_api_bp
from services.auth_service import (begin_mfa_setup, confirm_mfa_setup, recover_mfa,
                                   rebind_mfa, reset_user_mfa, verify_operation_code)
from services.base import ServiceError
from utils.permission import require_permission
from utils.settings import SECURITY_DEFAULTS, setting_bool, setting_int, setting_value
from utils.json_fields import parse_json
from models import SystemSetting, db
from app import limiter


def _service_call(func, *args):
    try:
        return func(*args), None
    except ServiceError as error:
        return None, fail(error.message, 400)


def mfa_context_required(func):
    """Allow a logged-in user or the five-minute password-authenticated bind session."""
    @wraps(func)
    def wrapper(*args, **kwargs):
        if current_user.is_authenticated:
            g.mfa_user = current_user
            g.mfa_pending_login = False
            return func(*args, **kwargs)
        user_id = session.get('pending_mfa_user_id')
        pending_at = session.get('pending_mfa_at')
        if not user_id or not pending_at or int(datetime.utcnow().timestamp()) - int(pending_at) > 300:
            return fail('登录验证已过期，请重新输入密码', 401)
        from models import User
        user = User.query.filter_by(id=int(user_id), is_active=True).first()
        if not user:
            return fail('账号不可用', 401)
        g.mfa_user = user
        g.mfa_pending_login = True
        return func(*args, **kwargs)
    return wrapper


@vue_api_bp.route('/api/auth/mfa/status', methods=['GET'])
@mfa_context_required
def api_mfa_status():
    user = g.mfa_user
    return ok({
        'login_enabled': bool(user.mfa_enabled),
        'operation_enabled': bool(user.mfa_op_enabled),
        'backup_codes_remaining': len(parse_json(user.backup_codes_json or '', default=[])),
        'mfa_enforce': setting_bool('mfa_enforce', False),
        'op_code_enforce': setting_bool('op_code_enforce', False),
    })


@vue_api_bp.route('/api/auth/security-profile', methods=['GET'])
@login_required
def api_security_profile():
    return ok({
        'mfa': {'login_enabled': bool(current_user.mfa_enabled),
                'operation_enabled': bool(current_user.mfa_op_enabled)},
        'operation_token_ttl_seconds': setting_int('op_code_ttl_seconds', 120, 30, 600),
        'session_idle_minutes': setting_int('session_idle_minutes', 30, 5, 1440),
    })


@vue_api_bp.route('/api/auth/mfa/setup', methods=['POST'])
@mfa_context_required
def api_mfa_setup():
    purpose = (request.get_json(silent=True) or {}).get('purpose', 'login')
    result, error = _service_call(begin_mfa_setup, g.mfa_user, purpose)
    if error:
        return error
    from blueprints.vue_api_sys import audit_log
    audit_log('mfa:setup_started', 'user', g.mfa_user.id, f'发起 {purpose} MFA 绑定')
    return ok(result)


@vue_api_bp.route('/api/auth/mfa/confirm', methods=['POST'])
@mfa_context_required
def api_mfa_confirm():
    data = request.get_json(silent=True) or {}
    user = g.mfa_user
    _, error = _service_call(confirm_mfa_setup, user,
                             data.get('purpose', 'login'), data.get('code', ''))
    if error:
        return error
    from blueprints.vue_api_sys import audit_log
    login_result = None
    if g.mfa_pending_login and data.get('purpose', 'login') == 'login':
        session.clear()
        login_user(user)
        from utils.session_security import establish_session
        establish_session(user)
        login_result = {'user': _user_payload(user)}
    audit_log('mfa:enabled', 'user', user.id,
              f'启用 {data.get("purpose", "login")} MFA')
    return ok(login_result)


@vue_api_bp.route('/api/auth/mfa/rebind', methods=['POST'])
@login_required
def api_mfa_rebind():
    data = request.get_json(silent=True) or {}
    result, error = _service_call(rebind_mfa, current_user,
                                  data.get('purpose', 'login'), data.get('current_code', ''))
    return error or ok(result)


@vue_api_bp.route('/api/auth/mfa/recover', methods=['POST'])
@login_required
def api_mfa_recover():
    data = request.get_json(silent=True) or {}
    _, error = _service_call(recover_mfa, current_user,
                             data.get('purpose', 'login'), data.get('recovery_code', ''))
    if error:
        return error
    from blueprints.vue_api_sys import audit_log
    audit_log('mfa:recovered', 'user', current_user.id, '使用恢复码解除 MFA 绑定')
    return ok(None)


@vue_api_bp.route('/api/auth/op-verify', methods=['POST'])
@limiter.limit('5 per minute;20 per hour')
@login_required
def api_operation_verify():
    code = (request.get_json(silent=True) or {}).get('code', '')
    result, error = _service_call(verify_operation_code, current_user, code)
    if error:
        return error
    return ok({'token': result,
               'expires_in': setting_int('op_code_ttl_seconds', 120, 30, 600)})


@vue_api_bp.route('/api/users/<int:user_id>/mfa-reset', methods=['POST'])
@login_required
@require_permission('mfa:manage')
def api_admin_mfa_reset(user_id):
    from models import User
    user = User.query.get_or_404(user_id)
    purpose = (request.get_json(silent=True) or {}).get('purpose', 'all')
    if purpose not in {'all', 'login', 'operation'}:
        return fail('MFA 用途非法', 400)
    reset_user_mfa(user, purpose)
    from blueprints.vue_api_sys import audit_log
    audit_log('mfa:admin_reset', 'user', user.id, f'管理员重置 {user.username} {purpose} MFA')
    return ok(None)


@vue_api_bp.route('/api/system/security-profile', methods=['GET'])
@login_required
@require_permission('system:security')
def api_system_security_profile():
    return ok({key: setting_value(key, default) for key, default in SECURITY_DEFAULTS.items()})


@vue_api_bp.route('/api/system/security-profile', methods=['PUT'])
@login_required
@require_permission('system:security')
def api_system_security_profile_update():
    data = request.get_json(silent=True) or {}
    allowed = set(SECURITY_DEFAULTS)
    unknown = set(data) - allowed
    if unknown:
        return fail(f'未知安全设置：{", ".join(sorted(unknown))}', 400)
    bool_keys = {'mfa_enforce', 'op_code_enforce', 'session_bind_ip'}
    int_ranges = {'op_code_ttl_seconds': (30, 600), 'session_idle_minutes': (5, 1440)}
    for key, value in data.items():
        if key in bool_keys:
            stored = '1' if str(value).lower() in {'1', 'true', 'yes', 'on'} else '0'
        elif key in int_ranges:
            try:
                number = int(value)
            except (TypeError, ValueError):
                return fail(f'{key} 必须为整数', 400)
            low, high = int_ranges[key]
            if not low <= number <= high:
                return fail(f'{key} 必须在 {low}-{high} 范围内', 400)
            stored = str(number)
        else:
            stored = str(value or '').strip()
            if len(stored) > 1000:
                return fail(f'{key} 内容过长', 400)
        row = SystemSetting.query.get(key)
        if row:
            row.value = stored
        else:
            db.session.add(SystemSetting(key=key, value=stored))
    db.session.commit()
    from blueprints.vue_api_sys import audit_log
    audit_log('security:settings_update', 'system', None,
              f'更新身份安全设置：{", ".join(sorted(data))}')
    return api_system_security_profile()
