"""Typed access to SystemSetting with compatibility-first defaults."""


SECURITY_DEFAULTS = {
    'mfa_enforce': '0',
    'op_code_enforce': '0',
    'op_code_ttl_seconds': '120',
    'session_idle_minutes': '30',
    'session_bind_ip': '0',
    'offboard_hook_url': '',
    'offboard_hook_cmd': '',
}


def setting_value(key, default=None):
    from models import SystemSetting
    fallback = SECURITY_DEFAULTS.get(key, '' if default is None else default)
    row = SystemSetting.query.get(key)
    return row.value if row is not None else fallback


def setting_bool(key, default=False):
    fallback = '1' if default else '0'
    return str(setting_value(key, fallback)).strip().lower() in {'1', 'true', 'yes', 'on'}


def setting_int(key, default, minimum=None, maximum=None):
    try:
        value = int(setting_value(key, str(default)))
    except (TypeError, ValueError):
        value = default
    if minimum is not None:
        value = max(minimum, value)
    if maximum is not None:
        value = min(maximum, value)
    return value
