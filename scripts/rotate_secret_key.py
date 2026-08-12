# -*- coding: utf-8 -*-
"""设备密码/凭证加密密钥（.secret.key）轮换工具。

轮换 = 旧密钥解密全部密文 → 新密钥重加密 → 备份旧密钥 → 原子替换密钥文件。
覆盖加密列：设备凭据、AI Key、一次性导出密码、用户 MFA 种子，以及通知渠道
config_json 内嵌的 *_encrypted 字段。

安全约定：
- 默认 dry-run（只统计 + 抽样验证旧密钥可解），--apply 才实际执行
- 执行前自动备份 .secret.key 到 .secret.key.bak.<时间戳>
- 全程单事务：任一行重加密/校验失败则整体回滚，密钥文件不动
- 建议先 `systemctl stop itsm` 再执行，避免运行中写入旧密文

用法（项目根目录）：
    python scripts/rotate_secret_key.py            # 预览
    python scripts/rotate_secret_key.py --apply    # 实际轮换
"""
import base64
import os
import shutil
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from cryptography.fernet import Fernet

from app import create_app
from models import (db, Device, DeviceCredential, PasswordHistory, AIConfig,
                    ExportFile, DeviceExportRequest, User, NotifyChannelConfig)
from utils.json_fields import dumps_json, parse_json

KEY_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '.secret.key')

# (模型, 加密列名)
_TARGETS = [
    (Device, 'password_encrypted'),
    (DeviceCredential, 'password_encrypted'),
    (PasswordHistory, 'password_encrypted'),
    (AIConfig, 'api_key_encrypted'),
    (ExportFile, 'file_password_encrypted'),
    (DeviceExportRequest, 'file_password_encrypted'),
    (User, 'mfa_secret_encrypted'),
    (User, 'mfa_op_secret_encrypted'),
]

_JSON_SECRET_KEYS = {'secret_encrypted', 'app_secret_encrypted', 'token_encrypted',
                     'api_key_encrypted', 'password_encrypted'}


def _b64dec(s):
    return base64.b64decode(s)


def _b64enc(b):
    return base64.b64encode(b).decode('utf-8')


def _collect_rows():
    """收集所有含非空密文的行: [(row, column_name), ...]"""
    rows = []
    for model, col in _TARGETS:
        for r in model.query.all():
            if getattr(r, col):
                rows.append((r, col))
    return rows


def _collect_json_rows():
    rows = []
    for record in NotifyChannelConfig.query.all():
        config = parse_json(record.config_json or '', default={}, field_name='notify_config')
        keys = [key for key in _JSON_SECRET_KEYS if config.get(key)] if isinstance(config, dict) else []
        if keys:
            rows.append((record, config, keys))
    return rows


def main():
    apply = '--apply' in sys.argv
    if not os.path.exists(KEY_FILE):
        print(f'密钥文件不存在: {KEY_FILE}')
        sys.exit(1)
    with open(KEY_FILE, 'rb') as f:
        old_key = f.read()
    old_f = Fernet(old_key)

    app = create_app()
    with app.app_context():
        rows = _collect_rows()
        json_rows = _collect_json_rows()
        encrypted_values = [(getattr(row, col), f'{type(row).__name__}#{row.id}.{col}')
                            for row, col in rows]
        encrypted_values.extend((config[key], f'NotifyChannelConfig#{row.id}.{key}')
                                for row, config, keys in json_rows for key in keys)
        print(f'扫描到 {len(encrypted_values)} 个密文值（普通列 {len(rows)}，JSON {len(json_rows)} 行）')
        # 全量验证旧密钥，避免抽样漏掉单条损坏记录。
        plain_values = {}
        for encrypted, identity in encrypted_values:
            try:
                plain_values[identity] = old_f.decrypt(_b64dec(encrypted))
            except Exception as error:
                print(f'❌ 旧密钥无法解密 {identity}: {error}')
                sys.exit(2)
        print(f'全量验证: {len(plain_values)}/{len(encrypted_values)} 可用旧密钥解密')
        if not apply:
            print('\n以上为预览（未写库/未动密钥文件）。确认后执行: '
                  'python scripts/rotate_secret_key.py --apply')
            return

        # ---- 实际轮换 ----
        new_key = Fernet.generate_key()
        new_f = Fernet(new_key)
        ts = datetime.now().strftime('%Y%m%d_%H%M%S')
        backup = f'{KEY_FILE}.bak.{ts}'
        shutil.copy2(KEY_FILE, backup)
        print(f'旧密钥已备份: {backup}')

        try:
            for row, col in rows:
                identity = f'{type(row).__name__}#{row.id}.{col}'
                plain = plain_values[identity]
                setattr(row, col, _b64enc(new_f.encrypt(plain)))
            for row, config, keys in json_rows:
                for key in keys:
                    identity = f'NotifyChannelConfig#{row.id}.{key}'
                    config[key] = _b64enc(new_f.encrypt(plain_values[identity]))
                row.config_json = dumps_json(config)
            db.session.flush()
            # 提交前用新密钥全量回读校验（任何一条不符则整体回滚）
            for row, col in rows:
                identity = f'{type(row).__name__}#{row.id}.{col}'
                again = new_f.decrypt(_b64dec(getattr(row, col)))  # 新密文解回
                if plain_values[identity] != again:
                    raise RuntimeError(f'校验失败: {type(row).__name__}#{row.id}.{col}')
            for row, config, keys in json_rows:
                for key in keys:
                    identity = f'NotifyChannelConfig#{row.id}.{key}'
                    if new_f.decrypt(_b64dec(config[key])) != plain_values[identity]:
                        raise RuntimeError(f'校验失败: {identity}')
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            print(f'❌ 轮换失败已回滚（密钥文件未变更）: {e}')
            sys.exit(3)

        # 原子替换密钥文件
        tmp_key = f'{KEY_FILE}.tmp'
        with open(tmp_key, 'wb') as f:
            f.write(new_key)
        os.replace(tmp_key, KEY_FILE)
        print(f'✅ 轮换完成：{len(rows)} 条密文已用新密钥重加密，密钥文件已更新。')
        print(f'⚠ 请妥善保管备份密钥 {backup}；确认系统运行正常后可安全销毁。')


if __name__ == '__main__':
    main()
