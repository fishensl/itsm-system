# -*- coding: utf-8 -*-
"""一次性敏感凭据传输信封的签发、绑定和原子消费。"""
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import json
import os
import uuid

from flask import current_app, request
from flask_login import current_user

from models import (CredentialDownloadTicket, CredentialEnvelopeChallenge,
                    Device, db)
from services.base import ServiceError
from utils.credential_envelope import (
    PROTOCOL,
    VERSION,
    b64url_decode,
    b64url_encode,
    canonical_json,
    decrypt_payload,
    decrypt_payload_bytes,
    derive_directional_keys,
    encrypt_payload,
    generate_key_pair,
    public_key_from_jwk,
    public_key_to_jwk,
    sha256_hex,
    unwrap_private_key,
    wrap_private_key,
)
from utils.json_fields import dumps_json, parse_json
from utils.permission import has_permission
from utils.session_security import credential_session_context
from utils.totp import verify_operation_token


GENERIC_ERROR = '安全信封无效或已失效，请重新操作'


@dataclass(frozen=True)
class PurposeRule:
    method: str
    path_template: str
    permission: str
    direction: str = 'c2s'
    target_type: str | None = None
    operation_verification: bool = True


CREDENTIAL_ENVELOPE_PURPOSES = {
    'device.password.create': PurposeRule(
        'POST', '/api/devices', 'device:add', target_type='device'),
    'device.password.update': PurposeRule(
        'PUT', '/api/devices/{target_id}', 'device:edit', target_type='device'),
    'device.password.reveal': PurposeRule(
        'POST', '/api/v2/devices/{target_id}/reveal-password', 'device:reveal',
        direction='both', target_type='device'),
    'device.password.import': PurposeRule(
        'POST', '/api/v2/devices/import', 'device:add', target_type='device_import'),
    'device.password.export_unlock': PurposeRule(
        'POST', '/api/v2/devices/export-password-download/{target_id}/authorize',
        'device:reveal', direction='both', target_type='device_export'),
    'backup.password.export': PurposeRule(
        'POST', '/api/system/backup/export', 'system:security', target_type='backup'),
    'backup.password.import': PurposeRule(
        'POST', '/api/system/backup/import', 'system:security', target_type='backup'),
    'ai.credential.create': PurposeRule(
        'POST', '/api/ai-config', 'ai:edit', target_type='ai_config'),
    'ai.credential.update': PurposeRule(
        'PUT', '/api/ai-config/{target_id}', 'ai:edit', target_type='ai_config'),
    'notification.credential.update': PurposeRule(
        'PUT', '/api/notify/channels/{target_id}', 'notify:edit',
        target_type='notify_channel'),
}


@dataclass
class ConsumedEnvelope:
    payload: dict | bytes
    challenge_id: str
    response_key: bytes | None
    response_aad: bytes
    history_id: str | None = None

    def encrypt_response(self, value):
        if self.response_key is None:
            raise ServiceError(GENERIC_ERROR)
        envelope = encrypt_payload(
            self.response_key, canonical_json(value), self.response_aad)
        envelope['challenge_id'] = self.challenge_id
        return envelope


def envelope_mode():
    value = str(current_app.config.get('CREDENTIAL_ENVELOPE_MODE', 'off')).lower()
    return value if value in {'off', 'optional', 'required'} else 'off'


def _configured_purposes():
    raw = current_app.config.get('CREDENTIAL_ENVELOPE_PURPOSES', '')
    if isinstance(raw, (list, tuple, set)):
        values = {str(item).strip() for item in raw if str(item).strip()}
    else:
        values = {item.strip() for item in str(raw or '').split(',') if item.strip()}
    return values or set(CREDENTIAL_ENVELOPE_PURPOSES)


def purpose_enabled(purpose):
    return envelope_mode() != 'off' and purpose in _configured_purposes()


def purpose_required(purpose):
    return envelope_mode() == 'required' and purpose in _configured_purposes()


def note_raw_credential_compat(purpose):
    """记录 optional 灰度中的旧明文调用，只记元数据、不记请求内容。"""
    if envelope_mode() == 'optional' and purpose in _configured_purposes():
        current_app.logger.warning(
            '凭据信封兼容调用 purpose=%s user_id=%s path=%s',
            purpose, getattr(current_user, 'id', None), request.path)


def _iso(value):
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat(timespec='milliseconds').replace('+00:00', 'Z')


def _parse_iso(value):
    try:
        return datetime.fromisoformat(str(value).replace('Z', '+00:00')).astimezone(
            timezone.utc).replace(tzinfo=None)
    except (TypeError, ValueError) as exc:
        raise ServiceError('当前登录会话上下文无效，请重新登录') from exc


def _normalize_id(value):
    return str(value) if value not in (None, '') else None


def _rule_path(rule, target_id):
    if '{target_id}' in rule.path_template and target_id is None:
        raise ServiceError('缺少敏感操作目标')
    return rule.path_template.format(target_id=target_id)


def _operation_binding(token, required):
    if not required or not _operation_enforced():
        return None
    if not token or not verify_operation_token(
            token, current_user.id, getattr(current_user, 'auth_version', 0)):
        raise ServiceError('需要操作动态码验证')
    secret = current_app.config['SECRET_KEY'].encode('utf-8')
    return hmac.new(secret, b'operation-token-v1:' + token.encode('utf-8'),
                    hashlib.sha256).hexdigest()


def _operation_enforced():
    from utils.settings import setting_bool
    return setting_bool('op_code_enforce', False)


def _wrapping_keys():
    configured = str(current_app.config.get('ENVELOPE_WRAP_KEY') or '')
    previous = str(current_app.config.get('ENVELOPE_PREVIOUS_WRAP_KEY') or '')

    def decode(value):
        if not value:
            return None
        try:
            return b64url_decode(value, expected_length=32)
        except ValueError as exc:
            raise RuntimeError('ITSM_ENVELOPE_WRAP_KEY 必须是 Base64url 编码的 32 字节密钥') from exc

    current = decode(configured)
    if current is None:
        if current_app.config.get('IS_PRODUCTION'):
            raise RuntimeError('生产环境未配置 ITSM_ENVELOPE_WRAP_KEY')
        current = hashlib.sha256(
            current_app.config['SECRET_KEY'].encode('utf-8') + b':dev-envelope-wrap').digest()
    return current, decode(previous)


def _wrap_aad(challenge_id, purpose, expires_at):
    return canonical_json({
        'challenge_id': challenge_id,
        'purpose': purpose,
        'expires_at': _iso(expires_at),
    })


def _base_context(row):
    return {
        'protocol': PROTOCOL,
        'version': VERSION,
        'challenge_id': row.id,
        'purpose': row.purpose,
        'user_id': row.user_id,
        'username': row.username_snapshot,
        'auth_version': row.auth_version,
        'auth_strength': row.auth_strength,
        'login_at': _iso(row.login_at),
        'mfa_verified_at': _iso(row.mfa_verified_at),
        'session_binding': row.session_binding_hash,
        'operation_binding': row.operation_binding_hash or 'not-required',
        'method': row.method,
        'path': row.path,
        'target_type': row.target_type or '',
        'target_id': row.target_id or '',
        'history_id': row.history_id or '',
        'issued_at': _iso(row.created_at),
        'expires_at': _iso(row.expires_at),
    }


def _aad(row, direction):
    context = _base_context(row)
    context['direction'] = direction
    return canonical_json(context)


def _check_target_scope(rule, target_id):
    if rule.target_type == 'device' and target_id is not None:
        device = Device.query.get(int(target_id))
        if not device:
            raise ServiceError('敏感操作目标不存在')
        from utils.customer_scope import require_device_access
        require_device_access(current_user, device)


def _validate_actor(rule, operation_token):
    if not has_permission(rule.permission, current_user):
        raise ServiceError('无权执行该敏感操作')
    session_context = credential_session_context(current_user)
    if not session_context:
        raise ServiceError('本次登录未完成 MFA，不能执行敏感凭据操作')
    binding = _operation_binding(operation_token, rule.operation_verification)
    return session_context, binding


def issue_challenge(purpose, client_public_key, target_id=None, history_id=None,
                    operation_token=''):
    if not purpose_enabled(purpose):
        raise ServiceError('凭据传输信封未启用')
    rule = CREDENTIAL_ENVELOPE_PURPOSES.get(purpose)
    if not rule:
        raise ServiceError('不支持的敏感操作用途')
    target_id = _normalize_id(target_id)
    history_id = _normalize_id(history_id)
    path = _rule_path(rule, target_id)
    session_context, operation_binding = _validate_actor(rule, operation_token)
    _check_target_scope(rule, target_id)
    public_key_from_jwk(client_public_key)

    now = datetime.utcnow()
    ttl = max(30, min(int(current_app.config.get(
        'ENVELOPE_CHALLENGE_TTL_SECONDS', 60)), 120))
    expires_at = now + timedelta(seconds=ttl)
    challenge_id = str(uuid.uuid4())
    private_key = generate_key_pair()
    public_jwk = public_key_to_jwk(private_key.public_key())
    salt = os.urandom(32)
    current_wrap_key, _ = _wrapping_keys()
    row = CredentialEnvelopeChallenge(
        id=challenge_id,
        user_id=current_user.id,
        username_snapshot=current_user.username,
        auth_version=session_context['auth_version'],
        auth_strength=session_context['auth_strength'],
        login_at=_parse_iso(session_context['login_at']),
        mfa_verified_at=_parse_iso(session_context['mfa_verified_at']),
        session_binding_hash=session_context['session_binding'],
        operation_binding_hash=operation_binding,
        purpose=purpose,
        method=rule.method,
        path=path,
        target_type=rule.target_type,
        target_id=target_id,
        history_id=history_id,
        client_public_jwk=dumps_json(client_public_key),
        server_public_jwk=dumps_json(public_jwk),
        wrap_kid=current_app.config.get('ENVELOPE_WRAP_KID', 'env-wrap-1'),
        salt=b64url_encode(salt),
        status='issued',
        created_at=now,
        expires_at=expires_at,
    )
    base = _base_context(row)
    row.context_hash = sha256_hex(canonical_json(base))
    row.server_private_key_wrapped = wrap_private_key(
        private_key, current_wrap_key,
        _wrap_aad(challenge_id, purpose, expires_at))
    db.session.add(row)
    (CredentialEnvelopeChallenge.query
     .filter(CredentialEnvelopeChallenge.status == 'issued',
             CredentialEnvelopeChallenge.expires_at < now)
     .update({'status': 'expired', 'server_private_key_wrapped': None},
             synchronize_session=False))
    db.session.commit()
    return {
        'version': VERSION,
        'challenge_id': row.id,
        'kid': row.wrap_kid,
        'server_public_key': public_jwk,
        'salt': row.salt,
        'context_hash': row.context_hash,
        'request_aad': b64url_encode(_aad(row, 'c2s')),
        'response_aad': b64url_encode(_aad(row, 's2c')),
        'expires_at': _iso(row.expires_at),
    }


def _validate_challenge_context(row, purpose, target_id, history_id, operation_token):
    rule = CREDENTIAL_ENVELOPE_PURPOSES[purpose]
    session_context, operation_binding = _validate_actor(rule, operation_token)
    expected_path = _rule_path(rule, _normalize_id(target_id))
    checks = (
        row.user_id == current_user.id,
        row.username_snapshot == current_user.username,
        row.auth_version == int(current_user.auth_version or 0),
        row.auth_strength == session_context['auth_strength'],
        row.session_binding_hash == session_context['session_binding'],
        row.operation_binding_hash == operation_binding,
        row.purpose == purpose,
        row.method == request.method,
        row.path == request.path == expected_path,
        row.target_id == _normalize_id(target_id),
        row.history_id == _normalize_id(history_id),
        row.context_hash == sha256_hex(canonical_json(_base_context(row))),
    )
    if not all(checks):
        raise ServiceError(GENERIC_ERROR)
    _check_target_scope(rule, target_id)


def consume_request_envelope(purpose, envelope, *, target_id=None, history_id=None,
                             operation_token='', max_plaintext=4096, binary=False):
    if not isinstance(envelope, dict) or envelope.get('version') != VERSION:
        raise ServiceError(GENERIC_ERROR)
    challenge_id = str(envelope.get('challenge_id') or '')
    try:
        uuid.UUID(challenge_id)
    except (ValueError, TypeError) as exc:
        raise ServiceError(GENERIC_ERROR) from exc
    now = datetime.utcnow()
    row = (CredentialEnvelopeChallenge.query
           .filter_by(id=challenge_id).with_for_update().first())
    if not row or row.status != 'issued' or row.expires_at <= now:
        if row and row.status == 'issued':
            row.status = 'expired'
            row.server_private_key_wrapped = None
            db.session.commit()
        raise ServiceError(GENERIC_ERROR)
    try:
        if history_id is None:
            history_id = row.history_id
        _validate_challenge_context(
            row, purpose, target_id, history_id, operation_token)
        current_wrap_key, previous_wrap_key = _wrapping_keys()
        wrap_aad = _wrap_aad(row.id, row.purpose, row.expires_at)
        try:
            private_key = unwrap_private_key(
                row.server_private_key_wrapped, current_wrap_key, wrap_aad)
        except Exception:
            if previous_wrap_key is None:
                raise
            private_key = unwrap_private_key(
                row.server_private_key_wrapped, previous_wrap_key, wrap_aad)
        client_key = public_key_from_jwk(parse_json(
            row.client_public_jwk, default={}, field_name='client_public_jwk'))
        c2s_key, s2c_key = derive_directional_keys(
            private_key, client_key, b64url_decode(row.salt, expected_length=32),
            row.id, row.context_hash)
        ciphertext_bytes = envelope.get('_ciphertext_bytes')
        if isinstance(ciphertext_bytes, bytes):
            plaintext = decrypt_payload_bytes(
                c2s_key, envelope.get('iv'), ciphertext_bytes, _aad(row, 'c2s'),
                max_plaintext=max_plaintext)
            ciphertext_hash = hashlib.sha256(ciphertext_bytes).hexdigest()
        else:
            ciphertext = str(envelope.get('ciphertext') or '')
            plaintext = decrypt_payload(
                c2s_key, envelope.get('iv'), ciphertext, _aad(row, 'c2s'),
                max_plaintext=max_plaintext)
            ciphertext_hash = hashlib.sha256(ciphertext.encode('ascii')).hexdigest()
        if binary:
            payload = plaintext
        else:
            payload = json.loads(plaintext.decode('utf-8'))
            if not isinstance(payload, dict):
                raise ValueError('信封载荷必须是对象')
    except ServiceError:
        row.status = 'rejected'
        row.server_private_key_wrapped = None
        row.used_at = now
        db.session.commit()
        raise
    except Exception as exc:
        row.status = 'rejected'
        row.server_private_key_wrapped = None
        row.used_at = now
        db.session.commit()
        current_app.logger.warning(
            '凭据信封拒绝 purpose=%s challenge=%s user_id=%s reason=invalid_envelope',
            purpose, challenge_id[:8], current_user.id)
        raise ServiceError(GENERIC_ERROR) from exc

    row.status = 'used'
    row.client_ciphertext_hash = ciphertext_hash
    row.server_private_key_wrapped = None
    row.used_at = now
    db.session.commit()
    current_app.logger.info(
        '凭据信封消费 purpose=%s challenge=%s user_id=%s',
        purpose, challenge_id[:8], current_user.id)
    return ConsumedEnvelope(
        payload=payload,
        challenge_id=row.id,
        response_key=s2c_key if CREDENTIAL_ENVELOPE_PURPOSES[purpose].direction == 'both' else None,
        response_aad=_aad(row, 's2c'),
        history_id=row.history_id,
    )


def consume_binary_request_envelope(purpose, *, challenge_id, iv, ciphertext,
                                    target_id=None, operation_token='', max_plaintext):
    return consume_request_envelope(
        purpose,
        {'version': VERSION, 'challenge_id': challenge_id, 'iv': iv,
         '_ciphertext_bytes': ciphertext},
        target_id=target_id,
        operation_token=operation_token,
        max_plaintext=max_plaintext,
        binary=True,
    )


def apply_credential_field(data, purpose, *, target_id=None, field='password'):
    """从普通 JSON 或信封提取单个敏感字段；required 模式拒绝 raw 字段。"""
    result = dict(data or {})
    envelope = result.pop('credential_envelope', None)
    raw_present = field in result and bool(result.get(field))
    if envelope:
        if raw_present:
            raise ServiceError('敏感字段不得同时以明文和信封提交')
        consumed = consume_request_envelope(
            purpose, envelope, target_id=target_id,
            operation_token=request.headers.get('X-Operation-Token', ''))
        value = consumed.payload.get(field)
        if not isinstance(value, str):
            raise ServiceError(GENERIC_ERROR)
        result[field] = value
        return result, True
    if raw_present and purpose_required(purpose):
        current_app.logger.warning(
            '拒绝明文敏感字段 purpose=%s user_id=%s', purpose, current_user.id)
        raise ServiceError('敏感字段必须使用凭据传输信封')
    if raw_present:
        note_raw_credential_compat(purpose)
    return result, False


def cleanup_credential_envelopes(now=None, retention_days=7):
    """清空过期私钥并删除保留期外元数据；不接触业务凭据密文。"""
    now = now or datetime.utcnow()
    cutoff = now - timedelta(days=max(int(retention_days), 1))
    expired = (CredentialEnvelopeChallenge.query
               .filter(CredentialEnvelopeChallenge.status == 'issued',
                       CredentialEnvelopeChallenge.expires_at <= now)
               .update({'status': 'expired', 'server_private_key_wrapped': None},
                       synchronize_session=False))
    deleted_challenges = (CredentialEnvelopeChallenge.query
                          .filter(CredentialEnvelopeChallenge.created_at < cutoff,
                                  CredentialEnvelopeChallenge.status != 'issued')
                          .delete(synchronize_session=False))
    deleted_tickets = (CredentialDownloadTicket.query
                       .filter(CredentialDownloadTicket.expires_at < cutoff)
                       .delete(synchronize_session=False))
    db.session.commit()
    return {
        'expired': expired,
        'deleted_challenges': deleted_challenges,
        'deleted_download_tickets': deleted_tickets,
    }
