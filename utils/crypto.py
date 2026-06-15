"""设备密码 AES 加密/解密模块"""
import os
import base64
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

# 密钥文件路径
KEY_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)), '.secret.key')


def _get_or_create_key() -> bytes:
    """获取或创建加密密钥"""
    if os.path.exists(KEY_FILE):
        with open(KEY_FILE, 'rb') as f:
            return f.read()
    # 创建新密钥
    key = Fernet.generate_key()
    with open(KEY_FILE, 'wb') as f:
        f.write(key)
    return key


def encrypt_password(password: str) -> str:
    """加密密码，返回 base64 字符串"""
    key = _get_or_create_key()
    f = Fernet(key)
    encrypted = f.encrypt(password.encode('utf-8'))
    return base64.b64encode(encrypted).decode('utf-8')


def decrypt_password(encrypted_data: str) -> str:
    """解密密码，返回明文"""
    key = _get_or_create_key()
    f = Fernet(key)
    try:
        encrypted = base64.b64decode(encrypted_data)
        return f.decrypt(encrypted).decode('utf-8')
    except Exception:
        return '【解密失败】'
