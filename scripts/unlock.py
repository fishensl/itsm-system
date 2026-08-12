"""Lock or unlock the optional wrapped application encryption key."""
import argparse
import getpass
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from utils.crypto import (KEY_FILE, WRAPPED_KEY_FILE, MasterKeyLocked,
                          lock_master_key, unlock_master_key)


def _password(confirm=False):
    value = getpass.getpass('管理员主密码: ')
    if confirm and value != getpass.getpass('再次输入管理员主密码: '):
        raise ValueError('两次输入的主密码不一致')
    if len(value) < 12:
        raise ValueError('管理员主密码至少需要 12 个字符')
    return value


def main():
    parser = argparse.ArgumentParser(description='ITSM 主密钥锁定/解锁工具')
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--lock', action='store_true', help='包装并删除明文 .secret.key')
    group.add_argument('--unlock', action='store_true', help='解包并恢复 .secret.key')
    group.add_argument('--check', action='store_true', help='只显示当前锁定状态')
    args = parser.parse_args()
    if args.check:
        state = 'unlocked' if os.path.exists(KEY_FILE) else (
            'locked' if os.path.exists(WRAPPED_KEY_FILE) else 'uninitialized')
        print(state)
        return
    try:
        if args.lock:
            lock_master_key(_password(confirm=True))
            print('主密钥已锁定；重启服务前请配置自动解锁或执行 --unlock。')
        else:
            unlock_master_key(_password(), persist=True)
            print('主密钥已解锁并原子恢复到 .secret.key。')
    except (FileNotFoundError, MasterKeyLocked, ValueError) as exc:
        parser.error(str(exc))


if __name__ == '__main__':
    main()
