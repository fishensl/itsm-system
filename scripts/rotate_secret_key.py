# -*- coding: utf-8 -*-
"""设备密码/凭证加密密钥（.secret.key）轮换工具。

轮换 = 旧密钥解密全部密文 → 新密钥重加密 → 备份旧密钥 → 原子替换密钥文件。
覆盖加密列：devices / device_credentials / password_history / ai_config 的 *_encrypted。

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
from models import db, Device, DeviceCredential, PasswordHistory, AIConfig

KEY_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '.secret.key')

# (模型, 加密列名)
_TARGETS = [
    (Device, 'password_encrypted'),
    (DeviceCredential, 'password_encrypted'),
    (PasswordHistory, 'password_encrypted'),
    (AIConfig, 'api_key_encrypted'),
]


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
        print(f'扫描到 {len(rows)} 条密文记录')
        # 抽样验证旧密钥可解
        sample_ok = 0
        for row, col in rows[:5]:
            try:
                old_f.decrypt(_b64dec(getattr(row, col)))
                sample_ok += 1
            except Exception:
                pass
        print(f'抽样验证（前5条）: {sample_ok}/{min(5, len(rows))} 可用旧密钥解密')
        if rows and sample_ok == 0:
            print('⚠ 抽样全部解密失败——密钥可能与数据不匹配，中止。')
            sys.exit(2)
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
                plain = old_f.decrypt(_b64dec(getattr(row, col)))
                setattr(row, col, _b64enc(new_f.encrypt(plain)))
            db.session.flush()
            # 提交前用新密钥全量回读校验（任何一条不符则整体回滚）
            for row, col in rows:
                check = old_f.decrypt(_b64dec(getattr(row, col)))  # 原明文
                again = new_f.decrypt(_b64dec(getattr(row, col)))  # 新密文解回
                if check != again:
                    raise RuntimeError(f'校验失败: {type(row).__name__}#{row.id}.{col}')
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
