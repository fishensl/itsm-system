"""Single password-policy boundary for self-service and administrator writes."""

MIN_PASSWORD_LENGTH = 12
KNOWN_DEFAULT_PASSWORDS = {
    'admin123',
    'changeme',
    'password',
    '123456',
    '12345678',
}


def password_policy_error(password: str) -> str | None:
    """Return a user-facing validation error, or None when the password is valid."""
    value = password or ''
    if len(value) < MIN_PASSWORD_LENGTH:
        return f'密码长度至少 {MIN_PASSWORD_LENGTH} 位'
    if value.strip().lower() in KNOWN_DEFAULT_PASSWORDS:
        return '不能使用系统默认或常见弱密码'
    return None
