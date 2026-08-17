#!/usr/bin/env python3
"""systemd timer 入口：按数据库中的备份时间/开关判断并执行一次备份。"""
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app import create_app  # noqa: E402
from utils.scheduler import run_scheduled_backup  # noqa: E402


def main() -> int:
    # 传入非空覆盖项，避免本进程再次启动 Web 内的业务 APScheduler。
    app = create_app({'SCHEDULED_BACKUP_RUNNER': True})
    with app.app_context():
        return run_scheduled_backup()


if __name__ == '__main__':
    raise SystemExit(main())
