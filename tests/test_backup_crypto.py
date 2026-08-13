# -*- coding: utf-8 -*-
"""W5 备份包密码保护：加密导出 → 识别 → 密码校验 → 解密导入 全链路"""
import os
import hashlib
import json
import zipfile

import pytest

from models import db, Customer
from utils.data_io import (
    build_export_zip, discard_import_restore, finalize_import_restore,
    is_encrypted_backup, perform_import,
)


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
            discard_import_restore(result)
        finally:
            os.remove(path)


def test_sha256_mismatch_is_hard_rejected(ctx, tmp_path):
    path, _, _ = build_export_zip()
    damaged = tmp_path / 'damaged.zip'
    try:
        with zipfile.ZipFile(path) as src, zipfile.ZipFile(damaged, 'w') as dst:
            for info in src.infolist():
                payload = src.read(info.filename)
                if info.filename == 'data.json':
                    payload += b' '
                dst.writestr(info, payload)
        with pytest.raises(ValueError, match='sha256'):
            perform_import(str(damaged))
    finally:
        os.remove(path)


def test_secret_key_is_published_only_after_finalize(ctx, tmp_path, monkeypatch):
    from cryptography.fernet import Fernet
    import utils.data_io as data_io

    old_key = Fernet.generate_key()
    new_key = Fernet.generate_key()
    (tmp_path / '.secret.key').write_bytes(old_key)
    data_json = b'{}'
    digest = hashlib.sha256(data_json + new_key).hexdigest()
    backup_path = tmp_path / 'key-restore.zip'
    with zipfile.ZipFile(backup_path, 'w') as zf:
        zf.writestr('data.json', data_json)
        zf.writestr('secret.key', new_key)
        zf.writestr('manifest.json', json.dumps({
            'format_version': 1,
            'table_columns': {},
            'sha256': digest,
        }))
    monkeypatch.setattr(data_io, '_app_root', lambda: str(tmp_path))

    result = perform_import(str(backup_path), restore_secret_key=True)
    assert (tmp_path / '.secret.key').read_bytes() == old_key
    finalize_import_restore(result)
    assert (tmp_path / '.secret.key').read_bytes() == new_key
