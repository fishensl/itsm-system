"""Run the outbox consumer independently of Gunicorn and APScheduler."""
import argparse
import os
import sys
import time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app
from models import db
from services.notification_worker import run_batch
from services.notification_jobs import periodic, cleanup


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--once', action='store_true')
    parser.add_argument('--cleanup', action='store_true')
    args = parser.parse_args()
    app = create_app({'NOTIFICATION_WORKER': True})
    last_periodic = 0
    last_cleanup = 0
    with app.app_context():
        if args.cleanup:
            print('清理记录数:', cleanup())
            return
        if db.engine.dialect.name != 'postgresql' and not args.once:
            raise SystemExit('持续消费者需要 PostgreSQL；SQLite 开发环境仅支持 --once')
        while True:
            try:
                if time.monotonic() - last_periodic > 60:
                    periodic()
                    last_periodic = time.monotonic()
                run_batch(5)
                if time.monotonic() - last_cleanup > 86400:
                    cleanup()
                    last_cleanup = time.monotonic()
            except Exception:
                db.session.rollback()
                app.logger.error('通知消费者本轮失败，请检查数据库与迁移状态')
                if args.once:
                    raise
            finally:
                db.session.remove()
            if args.once:
                break
            time.sleep(2)


if __name__ == '__main__':
    main()
