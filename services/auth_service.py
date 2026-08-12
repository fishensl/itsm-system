"""MFA and operation-code business rules (request-independent)."""
from datetime import datetime, timedelta

from services.base import ServiceError, transaction
from utils.crypto import decrypt_password, encrypt_password
from utils.json_fields import dumps_json, parse_json
from utils.totp import (consume_backup_code, generate_backup_codes, generate_secret,
                        hash_backup_codes, issue_operation_token, provisioning_uri,
                        qr_data_uri, verify_code)


def _purpose_fields(purpose):
    if purpose == 'login':
        return 'mfa_secret_encrypted', 'mfa_enabled', '登录'
    if purpose == 'operation':
        return 'mfa_op_secret_encrypted', 'mfa_op_enabled', '操作验证'
    raise ServiceError('MFA 用途非法')


@transaction
def begin_mfa_setup(user, purpose='login'):
    secret_field, enabled_field, label = _purpose_fields(purpose)
    if getattr(user, enabled_field, False):
        raise ServiceError(f'{label}验证器已绑定，请使用换绑流程')
    secret = generate_secret()
    backup_codes = generate_backup_codes()
    setattr(user, secret_field, encrypt_password(secret))
    setattr(user, enabled_field, False)
    user.backup_codes_json = dumps_json(hash_backup_codes(backup_codes))
    uri = provisioning_uri(secret, user.username, label)
    return {
        'purpose': purpose,
        'manual_secret': secret,
        'provisioning_uri': uri,
        'qr_data_uri': qr_data_uri(uri),
        'backup_codes': backup_codes,
    }


@transaction
def confirm_mfa_setup(user, purpose, code):
    secret_field, enabled_field, _ = _purpose_fields(purpose)
    encrypted = getattr(user, secret_field, None)
    if not encrypted:
        raise ServiceError('请先发起绑定')
    secret = decrypt_password(encrypted)
    if not verify_code(secret, code):
        raise ServiceError('动态验证码不正确')
    setattr(user, enabled_field, True)
    return True


def verify_user_mfa(user, purpose, code, allow_recovery=False):
    secret_field, enabled_field, _ = _purpose_fields(purpose)
    if not getattr(user, enabled_field, False):
        return False
    encrypted = getattr(user, secret_field, None)
    if encrypted:
        secret = decrypt_password(encrypted)
        if verify_code(secret, code):
            return True
    if allow_recovery:
        hashes = parse_json(user.backup_codes_json or '', default=[], field_name='backup_codes')
        matched, remaining = consume_backup_code(code, hashes)
        if matched:
            user.backup_codes_json = dumps_json(remaining)
            return True
    return False


@transaction
def rebind_mfa(user, purpose, current_code):
    if not verify_user_mfa(user, purpose, current_code, allow_recovery=True):
        raise ServiceError('当前动态码或恢复码不正确')
    secret_field, enabled_field, _ = _purpose_fields(purpose)
    setattr(user, secret_field, None)
    setattr(user, enabled_field, False)
    return begin_mfa_setup.__wrapped__(user, purpose)


@transaction
def recover_mfa(user, purpose, recovery_code):
    hashes = parse_json(user.backup_codes_json or '', default=[], field_name='backup_codes')
    matched, remaining = consume_backup_code(recovery_code, hashes)
    if not matched:
        raise ServiceError('恢复码无效')
    secret_field, enabled_field, _ = _purpose_fields(purpose)
    setattr(user, secret_field, None)
    setattr(user, enabled_field, False)
    user.backup_codes_json = dumps_json(remaining)
    return True


def verify_operation_code(user, code):
    from models import db
    now = datetime.utcnow()
    if user.op_locked_until and user.op_locked_until > now:
        seconds = max(1, int((user.op_locked_until - now).total_seconds()))
        raise ServiceError(f'操作验证已锁定，请 {seconds} 秒后重试')
    if not user.mfa_op_enabled:
        raise ServiceError('尚未绑定操作验证器')
    if verify_user_mfa(user, 'operation', code, allow_recovery=False):
        user.op_fail_count = 0
        user.op_locked_until = None
        token = issue_operation_token(user.id, user.auth_version)
        db.session.commit()
        return token
    user.op_fail_count = int(user.op_fail_count or 0) + 1
    locked = user.op_fail_count >= 5
    if locked:
        user.op_locked_until = now + timedelta(minutes=15)
        user.op_fail_count = 0
    db.session.commit()
    if locked:
        from utils.security_events import emit_security_event
        emit_security_event('操作验证码连续失败',
                            f'用户={user.username}，已锁定15分钟')
    raise ServiceError('操作动态码不正确')


@transaction
def reset_user_mfa(user, purpose='all'):
    if purpose in ('all', 'login'):
        user.mfa_secret_encrypted = None
        user.mfa_enabled = False
    if purpose in ('all', 'operation'):
        user.mfa_op_secret_encrypted = None
        user.mfa_op_enabled = False
        user.op_fail_count = 0
        user.op_locked_until = None
    user.backup_codes_json = '[]'
    user.auth_version = int(user.auth_version or 0) + 1
