"""RFC 6238 primitives, recovery codes and short-lived operation tokens."""
import base64
import hashlib
import hmac
import io
import secrets

import pyotp
from flask import current_app
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from werkzeug.security import check_password_hash, generate_password_hash

from utils.settings import setting_int


ISSUER = 'ITSM运维管理系统'


def generate_secret():
    return pyotp.random_base32()


def provisioning_uri(secret, username, purpose='登录'):
    account = f'{username}-{purpose}'
    return pyotp.TOTP(secret).provisioning_uri(name=account, issuer_name=ISSUER)


def qr_data_uri(uri):
    import qrcode
    image = qrcode.make(uri)
    stream = io.BytesIO()
    image.save(stream, format='PNG')
    return 'data:image/png;base64,' + base64.b64encode(stream.getvalue()).decode('ascii')


def verify_code(secret, code, valid_window=1):
    normalized = ''.join(ch for ch in str(code or '') if ch.isdigit())
    if len(normalized) != 6:
        return False
    return bool(pyotp.TOTP(secret).verify(normalized, valid_window=valid_window))


def generate_backup_codes(count=8):
    return [f'{secrets.token_hex(2).upper()}-{secrets.token_hex(2).upper()}' for _ in range(count)]


def hash_backup_codes(codes):
    return [generate_password_hash(code) for code in codes]


def consume_backup_code(code, hashes):
    for index, stored in enumerate(hashes or []):
        if check_password_hash(stored, str(code or '').strip().upper()):
            return True, hashes[:index] + hashes[index + 1:]
    return False, list(hashes or [])


def _serializer():
    return URLSafeTimedSerializer(current_app.config['SECRET_KEY'], salt='itsm-operation-token-v1')


def issue_operation_token(user_id, auth_version):
    nonce = secrets.token_urlsafe(8)
    return _serializer().dumps({'uid': int(user_id), 'av': int(auth_version or 0), 'n': nonce})


def verify_operation_token(token, user_id, auth_version):
    ttl = setting_int('op_code_ttl_seconds', 120, 30, 600)
    try:
        payload = _serializer().loads(token or '', max_age=ttl)
    except (BadSignature, SignatureExpired):
        return False
    return (hmac.compare_digest(str(payload.get('uid')), str(user_id)) and
            hmac.compare_digest(str(payload.get('av')), str(auth_version or 0)))


def secret_fingerprint(secret):
    return hashlib.sha256(secret.encode('ascii')).hexdigest()[:12]
