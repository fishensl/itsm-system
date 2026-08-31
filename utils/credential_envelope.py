# -*- coding: utf-8 -*-
"""P-256 ECDH + HKDF-SHA256 + AES-256-GCM 传输信封原语。"""
import base64
import hashlib
import json
import os

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF


PROTOCOL = 'itsm-credential-envelope'
VERSION = 1


def b64url_encode(value):
    return base64.urlsafe_b64encode(value).rstrip(b'=').decode('ascii')


def b64url_decode(value, *, expected_length=None, max_length=1_000_000):
    if not isinstance(value, str) or not value or len(value) > max_length * 2:
        raise ValueError('Base64url 参数无效')
    if any(ch not in 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_' for ch in value):
        raise ValueError('Base64url 参数无效')
    raw = base64.urlsafe_b64decode(value + '=' * (-len(value) % 4))
    if len(raw) > max_length or (expected_length is not None and len(raw) != expected_length):
        raise ValueError('Base64url 参数长度无效')
    return raw


def canonical_json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(',', ':')).encode('utf-8')


def sha256_hex(value):
    return hashlib.sha256(value).hexdigest()


def generate_key_pair():
    return ec.generate_private_key(ec.SECP256R1())


def public_key_to_jwk(public_key):
    numbers = public_key.public_numbers()
    return {
        'kty': 'EC',
        'crv': 'P-256',
        'x': b64url_encode(numbers.x.to_bytes(32, 'big')),
        'y': b64url_encode(numbers.y.to_bytes(32, 'big')),
        'ext': True,
    }


def public_key_from_jwk(jwk):
    if not isinstance(jwk, dict):
        raise ValueError('客户端公钥格式无效')
    if jwk.get('kty') != 'EC' or jwk.get('crv') != 'P-256':
        raise ValueError('客户端公钥算法无效')
    x = int.from_bytes(b64url_decode(jwk.get('x'), expected_length=32), 'big')
    y = int.from_bytes(b64url_decode(jwk.get('y'), expected_length=32), 'big')
    return ec.EllipticCurvePublicNumbers(x, y, ec.SECP256R1()).public_key()


def serialize_private_key(private_key):
    return private_key.private_bytes(
        serialization.Encoding.DER,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )


def deserialize_private_key(raw):
    key = serialization.load_der_private_key(raw, password=None)
    if not isinstance(key, ec.EllipticCurvePrivateKey) or not isinstance(key.curve, ec.SECP256R1):
        raise ValueError('服务端临时私钥算法无效')
    return key


def wrap_private_key(private_key, wrapping_key, aad):
    nonce = os.urandom(12)
    ciphertext = AESGCM(wrapping_key).encrypt(nonce, serialize_private_key(private_key), aad)
    return b64url_encode(nonce + ciphertext)


def unwrap_private_key(wrapped, wrapping_key, aad):
    raw = b64url_decode(wrapped, max_length=1024)
    if len(raw) < 29:
        raise ValueError('服务端临时私钥包装无效')
    return deserialize_private_key(AESGCM(wrapping_key).decrypt(raw[:12], raw[12:], aad))


def derive_directional_keys(private_key, peer_public_key, salt, challenge_id, context_hash):
    shared = private_key.exchange(ec.ECDH(), peer_public_key)
    base = f'{PROTOCOL}/v{VERSION}'.encode('ascii')
    challenge = challenge_id.encode('ascii')
    context = bytes.fromhex(context_hash)

    def derive(direction):
        return HKDF(
            algorithm=hashes.SHA256(), length=32, salt=salt,
            info=base + b'/' + direction + b'/' + challenge + b'/' + context,
        ).derive(shared)

    return derive(b'c2s'), derive(b's2c')


def decrypt_payload(key, iv_b64, ciphertext_b64, aad, *, max_plaintext=25 * 1024 * 1024):
    iv = b64url_decode(iv_b64, expected_length=12)
    ciphertext = b64url_decode(ciphertext_b64, max_length=max_plaintext + 16)
    if len(ciphertext) < 16:
        raise ValueError('信封密文无效')
    plaintext = AESGCM(key).decrypt(iv, ciphertext, aad)
    if len(plaintext) > max_plaintext:
        raise ValueError('信封明文超过限制')
    return plaintext


def decrypt_payload_bytes(key, iv_b64, ciphertext, aad, *, max_plaintext=25 * 1024 * 1024):
    iv = b64url_decode(iv_b64, expected_length=12)
    if not isinstance(ciphertext, bytes) or len(ciphertext) < 16 or len(ciphertext) > max_plaintext + 16:
        raise ValueError('信封密文无效')
    plaintext = AESGCM(key).decrypt(iv, ciphertext, aad)
    if len(plaintext) > max_plaintext:
        raise ValueError('信封明文超过限制')
    return plaintext


def encrypt_payload(key, plaintext, aad):
    iv = os.urandom(12)
    ciphertext = AESGCM(key).encrypt(iv, plaintext, aad)
    return {'version': VERSION, 'iv': b64url_encode(iv),
            'ciphertext': b64url_encode(ciphertext)}
