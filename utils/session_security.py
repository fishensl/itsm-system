"""Session revocation, idle timeout, MFA context and optional IP binding."""
from datetime import datetime, timezone
import base64
import hashlib
import hmac
import secrets

from flask import current_app, request, session
from flask_login import current_user, logout_user

from utils.access_control import client_ip
from utils.settings import setting_bool, setting_int


def _utc_iso(now=None):
    now = now or datetime.now(timezone.utc)
    return now.isoformat(timespec='milliseconds').replace('+00:00', 'Z')


def establish_session(user, auth_strength='password'):
    now = datetime.now(timezone.utc)
    session['auth_version'] = int(user.auth_version or 0)
    session['last_activity'] = int(now.timestamp())
    session['login_ip'] = client_ip()
    session['login_ua'] = (request.user_agent.string or '')[:256]
    session['login_at'] = _utc_iso(now)
    session['auth_strength'] = auth_strength
    session['mfa_verified_at'] = _utc_iso(now) if auth_strength.startswith('mfa_') else ''
    session['session_nonce'] = secrets.token_urlsafe(32)


def session_binding_hash():
    nonce = session.get('session_nonce') or ''
    if not nonce:
        return ''
    digest = hmac.new(
        current_app.config['SECRET_KEY'].encode('utf-8'),
        f'itsm-session-binding-v1:{nonce}'.encode('utf-8'),
        hashlib.sha256,
    ).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b'=').decode('ascii')


def credential_session_context(user):
    """返回 challenge 可绑定的权威会话上下文；未完成 MFA 时返回 None。"""
    strength = str(session.get('auth_strength') or '')
    binding = session_binding_hash()
    login_at = str(session.get('login_at') or '')
    verified_at = str(session.get('mfa_verified_at') or '')
    if (not strength.startswith('mfa_') or not binding or not login_at or not verified_at or
            int(session.get('auth_version', -1)) != int(user.auth_version or 0)):
        return None
    return {
        'auth_version': int(user.auth_version or 0),
        'auth_strength': strength,
        'login_at': login_at,
        'mfa_verified_at': verified_at,
        'session_binding': binding,
    }


def register_session_security(app):
    @app.before_request
    def enforce_session_policy():
        if not current_user.is_authenticated:
            return None
        now = int(datetime.now(timezone.utc).timestamp())
        last = session.get('last_activity')
        idle_seconds = setting_int('session_idle_minutes', 30, 5, 1440) * 60
        if last is not None and now - int(last) > idle_seconds:
            logout_user()
            session.clear()
            return None
        if setting_bool('session_bind_ip', False):
            bound = session.get('login_ip')
            if bound and bound != client_ip():
                logout_user()
                session.clear()
                return None
        session['last_activity'] = now
        session.modified = True
        return None
