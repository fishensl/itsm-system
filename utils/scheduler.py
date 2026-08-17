# -*- coding: utf-8 -*-
"""后台调度（APScheduler）：每日自动任务生成 + 逾期提醒。

- 合同自动巡检：每日补生成（按 last_generated_date 游标，幂等）
- 客户巡检频率：每日回填本年度任务（幂等 upsert）
- 逾期任务提醒：通知指派工程师
- 防重启动：dev reloader 仅子进程；生产多 worker 用 instance/scheduler.lock PID 锁
- 数据备份不再挂在 Gunicorn worker 内，改由 itsm-backup.timer 调用 run_scheduled_backup.py
"""
import logging
import os
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

log = logging.getLogger('itsm.scheduler')

_scheduler = None


def _daily_job():
    from models import db
    try:
        created_contract = 0
        created_customer = 0
        notified = 0
        timeout_notified = 0
        contract_notified = 0
        suspend_notified = 0
        try:
            from utils.auto_task_generator import generate_contract_tasks
            created_contract = len(generate_contract_tasks())
        except Exception:
            db.session.rollback()
            log.exception('调度：合同自动任务生成失败')
        try:
            from utils.customer_task_generator import generate_for_all_customers
            created_customer = generate_for_all_customers()
        except Exception:
            db.session.rollback()
            log.exception('调度：客户频率任务生成失败')
        try:
            from utils.notifications import notify_overdue_tasks
            notified = notify_overdue_tasks()
        except Exception:
            db.session.rollback()
            log.exception('调度：逾期提醒失败')
        try:
            from utils.notifications import notify_review_timeout
            timeout_notified = notify_review_timeout()
        except Exception:
            db.session.rollback()
            log.exception('调度：审核超时提醒失败')
        try:
            from utils.notifications import notify_contract_expiring
            contract_notified = notify_contract_expiring()
        except Exception:
            db.session.rollback()
            log.exception('调度：客户合同到期提醒失败')
        try:
            from utils.notifications import notify_suspended_tickets
            suspend_notified = notify_suspended_tickets()
        except Exception:
            db.session.rollback()
            log.exception('调度：工单挂起超时提醒失败')
        if created_contract or created_customer or notified or timeout_notified \
                or contract_notified or suspend_notified:
            log.info('调度完成：合同任务 +%d，客户任务 +%d，逾期提醒 %d 人，审核超时提醒 %d 条，'
                     '合同到期提醒 %d 条，挂起超时提醒 %d 条',
                     created_contract, created_customer, notified, timeout_notified,
                     contract_notified, suspend_notified)
    except Exception:
        log.exception('调度任务执行异常')


def _backup_job():
    """每日自动备份（Web 备份管理启用时执行 backup.sh；未启用/失败仅记日志不阻断）"""
    from models import db
    try:
        from utils.backup_config import get_backup_config
        cfg = get_backup_config()
        if cfg.get('backup_enabled') != '1':
            return 0
    except Exception:
        log.exception('调度：读取备份配置失败')
        return 0
    import subprocess
    import time
    from utils.backup_config import record_backup_result
    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    script = os.path.join(base, 'scripts', 'backup.sh')
    if not os.path.isfile(script):
        log.warning('调度：backup.sh 不存在（%s），跳过自动备份', script)
        status = record_backup_result(False, 'backup.sh 不存在')
        from utils.notifications import notify_backup_failure
        notify_backup_failure(f'备份脚本不存在；连续失败 {status["consecutive_failures"]} 次')
        return 0
    try:
        started = time.monotonic()
        env = dict(os.environ)
        keep = cfg.get('backup_keep') or '30'
        env['ITSM_BACKUP_KEEP'] = keep
        result = subprocess.run(
            ['bash', script, base],
            env=env, capture_output=True, text=True, timeout=1800)
        if result.returncode == 0:
            record_backup_result(True, duration_seconds=time.monotonic() - started)
            log.info('调度：自动备份完成（保留 %s 份）', keep)
            return 1
        error = f'backup.sh 返回码 {result.returncode}: {result.stderr[-300:]}'
        status = record_backup_result(False, error, time.monotonic() - started)
        log.error('调度：自动备份失败 rc=%s\n%s', result.returncode, result.stderr[-1000:])
        from utils.notifications import notify_backup_failure
        notify_backup_failure(
            f'backup.sh 返回码 {result.returncode}；连续失败 {status["consecutive_failures"]} 次')
    except Exception as exc:
        db.session.rollback()
        log.exception('调度：自动备份执行异常')
        try:
            status = record_backup_result(False, f'{type(exc).__name__}: {exc}')
            from utils.notifications import notify_backup_failure
            notify_backup_failure(
                f'自动备份执行异常；连续失败 {status["consecutive_failures"]} 次')
        except Exception:
            db.session.rollback()
            log.exception('调度：记录备份失败状态或发送告警时异常')
    return 0


def _parse_status_time(value):
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=ZoneInfo('UTC'))
        return parsed
    except (TypeError, ValueError):
        return None


def backup_is_due(config, status, now=None):
    """判断 systemd timer 本轮是否应执行备份（上海时区，每次失败一小时后重试）。"""
    if str(config.get('backup_enabled', '0')) != '1':
        return False
    local_tz = ZoneInfo('Asia/Shanghai')
    now = now or datetime.now(local_tz)
    if now.tzinfo is None:
        now = now.replace(tzinfo=local_tz)
    else:
        now = now.astimezone(local_tz)
    try:
        hour, minute = (int(part) for part in str(config.get('backup_time', '03:00')).split(':', 1))
        scheduled = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    except (TypeError, ValueError):
        return False
    if now < scheduled:
        return False

    last_success = _parse_status_time(status.get('last_success_at'))
    if last_success and last_success.astimezone(local_tz).date() >= now.date():
        return False
    last_attempt = _parse_status_time(status.get('last_attempt_at'))
    if last_attempt:
        local_attempt = last_attempt.astimezone(local_tz)
        if local_attempt >= scheduled and now - local_attempt < timedelta(hours=1):
            return False
    return True


def run_scheduled_backup(now=None):
    """供独立 systemd timer 调用。返回 0=无需执行/成功，1=应执行但失败。"""
    from utils.backup_config import get_backup_config, get_backup_status
    config = get_backup_config()
    status = get_backup_status()
    if not backup_is_due(config, status, now=now):
        log.info('备份 timer 检查完成：当前无需执行')
        return 0
    return 0 if _backup_job() == 1 else 1


def _acquire_lock():
    """PID 锁文件：返回持有锁时删除用路径，未抢到返回 None"""
    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    lock_path = os.path.join(base, 'instance', 'scheduler.lock')
    try:
        with open(lock_path, 'r') as f:
            old_pid = int(f.read().strip())
        if old_pid > 0 and old_pid != os.getpid():
            try:
                os.kill(old_pid, 0)
                return None  # 已有存活实例持有锁
            except OSError:
                pass  # 原进程已退出，可抢占
    except (FileNotFoundError, ValueError):
        pass
    try:
        with open(lock_path, 'w') as f:
            f.write(str(os.getpid()))
        return lock_path
    except OSError:
        return None


def start_scheduler(app):
    """启动后台调度器（幂等；防多实例）"""
    global _scheduler
    if _scheduler is not None:
        return _scheduler
    # dev（flask debug reloader）：仅 werkzeug 子进程启动，父进程跳过
    if app.debug and os.environ.get('WERKZEUG_RUN_MAIN') != 'true':
        return None
    # 生产：多 worker / 多进程场景由 PID 锁保证单实例
    lock_path = _acquire_lock()
    if lock_path is None and not app.debug:
        return None
    s = BackgroundScheduler(timezone='Asia/Shanghai')
    s.add_job(_daily_job, CronTrigger(hour=8, minute=30), id='itsm-daily', replace_existing=True)
    s.start()
    _scheduler = s

    def _release():
        try:
            if lock_path and os.path.exists(lock_path):
                os.remove(lock_path)
        except OSError:
            pass

    if lock_path:
        import atexit
        atexit.register(_release)
    log.info('后台业务调度器已启动（每日 08:30：自动任务生成 + 逾期提醒）；备份由 systemd timer 执行')
    return s


def reschedule_backup():
    """systemd timer 每五分钟读取数据库配置，无需进程内重排。"""
    return None
