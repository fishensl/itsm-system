# -*- coding: utf-8 -*-
"""后台调度（APScheduler）：每日自动任务生成 + 逾期提醒

- 合同自动巡检：每日补生成（按 last_generated_date 游标，幂等）
- 客户巡检频率：每日回填本年度任务（幂等 upsert）
- 逾期任务提醒：通知指派工程师
- 防重启动：dev reloader 仅子进程；生产多 worker 用 instance/scheduler.lock PID 锁
"""
import logging
import os

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
        if created_contract or created_customer or notified:
            log.info('调度完成：合同任务 +%d，客户任务 +%d，逾期提醒 %d 人',
                     created_contract, created_customer, notified)
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
    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    script = os.path.join(base, 'scripts', 'backup.sh')
    if not os.path.isfile(script):
        log.warning('调度：backup.sh 不存在（%s），跳过自动备份', script)
        return 0
    try:
        env = dict(os.environ)
        keep = cfg.get('backup_keep') or '30'
        env['ITSM_BACKUP_KEEP'] = keep
        result = subprocess.run(
            ['bash', script, base],
            env=env, capture_output=True, text=True, timeout=1800)
        if result.returncode == 0:
            log.info('调度：自动备份完成（保留 %s 份）', keep)
            return 1
        log.error('调度：自动备份失败 rc=%s\n%s', result.returncode, result.stderr[-1000:])
    except Exception:
        db.session.rollback()
        log.exception('调度：自动备份执行异常')
    return 0


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
    try:
        from utils.backup_config import backup_time_trigger
        bh, bm = backup_time_trigger()
    except Exception:
        bh, bm = 3, 0
    s.add_job(_backup_job, CronTrigger(hour=bh, minute=bm),
              id='itsm-backup', replace_existing=True)
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
    log.info('后台调度器已启动（每日 08:30：自动任务生成 + 逾期提醒；每日 %02d:%02d：自动备份）',
             _scheduler.get_job('itsm-backup').trigger.hour if _scheduler.get_job('itsm-backup') else 3,
             _scheduler.get_job('itsm-backup').trigger.minute if _scheduler.get_job('itsm-backup') else 0)
    return s


def reschedule_backup():
    """备份配置变更后重排备份任务（幂等；未启动调度器时忽略）"""
    global _scheduler
    if _scheduler is None:
        return
    try:
        from utils.backup_config import backup_time_trigger
        bh, bm = backup_time_trigger()
        job = _scheduler.get_job('itsm-backup')
        if job and (job.trigger.hour != bh or job.trigger.minute != bm):
            job.reschedule(CronTrigger(hour=bh, minute=bm))
            log.info('备份任务重排为每日 %02d:%02d', bh, bm)
    except Exception:
        log.exception('备份任务重排失败')
