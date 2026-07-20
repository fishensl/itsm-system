# -*- coding: utf-8 -*-
"""W5 备份包密码保护：加密导出 → 识别 → 密码校验 → 解密导入 全链路"""
import os
import zipfile

import pytest

from models import db, Customer
from utils.data_io import build_export_zip, perform_import, is_encrypted_backup


@pytest.fixture()
def ctx(app):
    with app.app_context():
        db.session.add(Customer(name='备份测试客户'))
        db.session.commit()
        yield


class TestPlainExport:
    def test_plain_zip_not_encrypted(self, ctx):
        path, size, manifest = build_export_zip()
        try:
            assert not is_encrypted_backup(path)
            with zipfile.ZipFile(path) as zf:
                assert 'manifest.json' in zf.namelist()
                assert 'data.json' in zf.namelist()
        finally:
            os.remove(path)


class TestEncryptedExportImport:
    def test_encrypted_export_detected_and_not_zip(self, ctx):
        path, _, _ = build_export_zip(password='S3cret密码')
        try:
            assert is_encrypted_backup(path)
            with pytest.raises(zipfile.BadZipFile):
                zipfile.ZipFile(path)
        finally:
            os.remove(path)

    def test_wrong_password_rejected(self, ctx):
        path, _, _ = build_export_zip(password='right-pwd')
        try:
            with pytest.raises(ValueError, match='密码错误|损坏'):
                perform_import(path, password='wrong-pwd')
        finally:
            os.remove(path)

    def test_missing_password_rejected(self, ctx):
        path, _, _ = build_export_zip(password='right-pwd')
        try:
            with pytest.raises(ValueError, match='已加密'):
                perform_import(path)
        finally:
            os.remove(path)

    def test_correct_password_roundtrip(self, ctx, app):
        """正确密码 → 解密 → 完整导入恢复数据"""
        path, _, _ = build_export_zip(password='right-pwd')
        try:
            result = perform_import(path, password='right-pwd')
            assert result['restored_rows'] > 0
            assert Customer.query.filter_by(name='备份测试客户').first() is not None
        finally:
            os.remove(path)
