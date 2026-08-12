# -*- coding: utf-8 -*-
"""密码加解密：Fernet 往返 + 篡改容错（不泄露异常）"""
import pytest

from utils.crypto import encrypt_password, decrypt_password


class TestCryptoRoundtrip:
    def test_roundtrip(self):
        for plain in ['S3cret!密码', 'a', 'x' * 500, '!@#$%^&*()_+-=[]{}']:
            assert decrypt_password(encrypt_password(plain)) == plain

    def test_ciphertext_differs_from_plaintext(self):
        ct = encrypt_password('topsecret')
        assert 'topsecret' not in ct

    def test_tampered_ciphertext_returns_placeholder(self):
        """解密失败返回占位符而非抛异常（页面不崩、不泄露细节）"""
        assert decrypt_password('not-a-valid-fernet-token') == '【解密失败】'

    def test_empty_input(self):
        assert decrypt_password('') == '【解密失败】'


def test_optional_master_key_lock_roundtrip(tmp_path, monkeypatch):
    from cryptography.fernet import Fernet
    import utils.crypto as crypto

    key_file = tmp_path / '.secret.key'
    wrapped_file = tmp_path / '.secret.key.locked'
    original = Fernet.generate_key()
    key_file.write_bytes(original)
    monkeypatch.setattr(crypto, 'KEY_FILE', str(key_file))
    monkeypatch.setattr(crypto, 'WRAPPED_KEY_FILE', str(wrapped_file))
    monkeypatch.setattr(crypto, '_memory_key', None)

    crypto.lock_master_key('correct horse battery staple')
    assert not key_file.exists()
    assert wrapped_file.exists()
    with pytest.raises(crypto.MasterKeyLocked):
        crypto.ensure_master_key_available()

    monkeypatch.setenv('ITSM_AUTO_UNLOCK_KEY', 'correct horse battery staple')
    crypto.ensure_master_key_available()
    assert crypto._memory_key == original
    assert not key_file.exists()


def test_wrapped_master_key_rejects_wrong_password():
    import utils.crypto as crypto
    from cryptography.fernet import Fernet

    envelope = crypto.wrap_master_key(Fernet.generate_key(), 'correct horse battery staple')
    with pytest.raises(crypto.MasterKeyLocked):
        crypto.unwrap_master_key(envelope, 'wrong password')
