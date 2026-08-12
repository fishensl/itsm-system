"""Session revocation, idle timeout and optional IP binding."""
from datetime import datetime, timezone

from flask import request, session
from flask_login import current_user, logout_user

from utils.access_control import client_ip
from utils.settings import setting_bool, setting_int


def establish_session(user):
    session['auth_version'] = int(user.auth_version or 0)
    session['last_activity'] = int(datetime.now(timezone.utc).timestamp())
    session['login_ip'] = client_ip()
    session['login_ua'] = (request.user_agent.string or '')[:256]


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
