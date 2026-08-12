"""Revoke access while retaining all historical business records."""
from services.base import ServiceError, transaction


@transaction
def offboard_user(user, actor_id=None):
    if actor_id is not None and user.id == actor_id:
        raise ServiceError('不能对当前登录账号执行离职清理')
    snapshot = {
        'username': user.username,
        'realname': user.realname or '',
        'vpn_account': user.vpn_account or '',
    }
    user.is_active = False
    user.auth_version = int(user.auth_version or 0) + 1
    user.mfa_secret_encrypted = None
    user.mfa_enabled = False
    user.mfa_op_secret_encrypted = None
    user.mfa_op_enabled = False
    user.backup_codes_json = '[]'
    user.op_fail_count = 0
    user.op_locked_until = None
    user.login_fail_count = 0
    user.login_locked_until = None
    return snapshot


def run_offboard_hooks(snapshot):
    """Best-effort hooks. Command uses argv without a shell; failures are returned only."""
    import shlex
    import subprocess

    import requests

    from utils.settings import setting_value
    errors = []
    url = str(setting_value('offboard_hook_url', '') or '').strip()
    if url:
        try:
            requests.post(url, json=snapshot, timeout=8).raise_for_status()
        except Exception as error:
            errors.append(f'URL hook: {error}')
    command = str(setting_value('offboard_hook_cmd', '') or '').strip()
    if command:
        try:
            args = shlex.split(command, posix=False)
            subprocess.run(args + [snapshot['username'], snapshot['vpn_account'], snapshot['realname']],
                           shell=False, check=True, timeout=15, capture_output=True)
        except Exception as error:
            errors.append(f'command hook: {error}')
    return errors
