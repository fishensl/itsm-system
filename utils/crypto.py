"""Fernet field encryption with an optional PBKDF2/AES-GCM wrapped master key."""
import base64
import json
import os
import tempfile

from cryptography.exceptions import InvalidTag
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC


ROOT_DIR = os.path.dirname(os.path.dirname(__file__))
KEY_FILE = os.path.join(ROOT_DIR, '.secret.key')
WRAPPED_KEY_FILE = os.path.join(ROOT_DIR, '.secret.key.locked')
PBKDF2_ITERATIONS = 480_000
_memory_key: bytes | None = None


class MasterKeyLocked(RuntimeError):
    """The wrapped master key exists but no valid unlock secret was supplied."""


def _atomic_write(path: str, payload: bytes) -> None:
    directory = os.path.dirname(path) or '.'
    fd, tmp_path = tempfile.mkstemp(prefix='.key-', dir=directory)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        try:
            os.chmod(tmp_path, 0o600)
        except OSError:
            pass
        os.replace(tmp_path, path)
    finally:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)


def _derive_kek(password: str, salt: bytes, iterations: int = PBKDF2_ITERATIONS) -> bytes:
    if not password:
        raise ValueError('主密钥密码不能为空')
    return PBKDF2HMAC(
        algorithm=hashes.SHA256(), length=32, salt=salt, iterations=iterations,
    ).derive(password.encode('utf-8'))


def wrap_master_key(master_key: bytes, password: str) -> bytes:
    """Return a versioned JSON envelope containing an AES-256-GCM wrapped key."""
    Fernet(master_key)  # validate the existing application key before wrapping it
    salt, nonce = os.urandom(16), os.urandom(12)
    kek = _derive_kek(password, salt)
    ciphertext = AESGCM(kek).encrypt(nonce, master_key, b'itsm-master-key-v1')
    return json.dumps({
        'version': 1,
        'kdf': 'pbkdf2-sha256',
        'iterations': PBKDF2_ITERATIONS,
        'salt': base64.b64encode(salt).decode('ascii'),
        'nonce': base64.b64encode(nonce).decode('ascii'),
        'ciphertext': base64.b64encode(ciphertext).decode('ascii'),
    }, separators=(',', ':')).encode('utf-8')


def unwrap_master_key(envelope: bytes, password: str) -> bytes:
    try:
        value = json.loads(envelope.decode('utf-8'))
        if value.get('version') != 1 or value.get('kdf') != 'pbkdf2-sha256':
            raise ValueError('不支持的主密钥包装格式')
        iterations = int(value['iterations'])
        if iterations < PBKDF2_ITERATIONS:
            raise ValueError('主密钥包装迭代次数低于安全基线')
        salt = base64.b64decode(value['salt'], validate=True)
        nonce = base64.b64decode(value['nonce'], validate=True)
        ciphertext = base64.b64decode(value['ciphertext'], validate=True)
        key = AESGCM(_derive_kek(password, salt, iterations)).decrypt(
            nonce, ciphertext, b'itsm-master-key-v1')
        Fernet(key)
        return key
    except (InvalidTag, KeyError, TypeError, json.JSONDecodeError, ValueError) as exc:
        raise MasterKeyLocked('主密钥密码错误或包装文件损坏') from exc


def lock_master_key(password: str, *, remove_plaintext: bool = True) -> str:
    """Wrap the existing key; removing plaintext makes subsequent starts locked."""
    global _memory_key
    if not os.path.exists(KEY_FILE):
        raise FileNotFoundError('未找到 .secret.key，无法锁定')
    with open(KEY_FILE, 'rb') as stream:
        key = stream.read().strip()
    _atomic_write(WRAPPED_KEY_FILE, wrap_master_key(key, password))
    if remove_plaintext:
        os.unlink(KEY_FILE)
        _memory_key = None
    return WRAPPED_KEY_FILE


def unlock_master_key(password: str, *, persist: bool = False) -> bytes:
    """Unlock into process memory or atomically restore the legacy plaintext key file."""
    global _memory_key
    with open(WRAPPED_KEY_FILE, 'rb') as stream:
        key = unwrap_master_key(stream.read(), password)
    if persist:
        _atomic_write(KEY_FILE, key)
    else:
        _memory_key = key
    return key


def ensure_master_key_available() -> None:
    """Fail fast during startup when a locked deployment cannot be unlocked."""
    _get_or_create_key()


def _get_or_create_key() -> bytes:
    global _memory_key
    if _memory_key:
        return _memory_key
    if os.path.exists(KEY_FILE):
        with open(KEY_FILE, 'rb') as stream:
            return stream.read().strip()
    if os.path.exists(WRAPPED_KEY_FILE):
        auto_key = os.environ.get('ITSM_AUTO_UNLOCK_KEY', '')
        if not auto_key:
            raise MasterKeyLocked(
                '主密钥已锁定；请执行 scripts/unlock.py，或配置 ITSM_AUTO_UNLOCK_KEY')
        return unlock_master_key(auto_key, persist=False)
    key = Fernet.generate_key()
    _atomic_write(KEY_FILE, key)
    return key


def encrypt_password(password: str) -> str:
    encrypted = Fernet(_get_or_create_key()).encrypt(password.encode('utf-8'))
    return base64.b64encode(encrypted).decode('utf-8')


def decrypt_password(encrypted_data: str) -> str:
    try:
        encrypted = base64.b64decode(encrypted_data)
        return Fernet(_get_or_create_key()).decrypt(encrypted).decode('utf-8')
    except MasterKeyLocked:
        raise
    except Exception:
        return '【解密失败】'
