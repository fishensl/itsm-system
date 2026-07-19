# -*- coding: utf-8 -*-
"""密码加解密：Fernet 往返 + 篡改容错（不泄露异常）"""
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
