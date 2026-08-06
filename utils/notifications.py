# -*- coding: utf-8 -*-
"""站内通知统一入口（service 层 / 蓝图共用，失败不阻断主流程）"""


def notify(user_id, category, title, content='', link=''):
    """写入站内通知（独立提交：调用方事务已 commit 后再调用，失败仅影响通知本身）"""
    if not user_id:
        return
    from models import db, Notification
    try:
        db.session.add(Notification(
            user_id=user_id, category=category, title=(title or '')[:128],
            content=(content or '')[:500], link=link or ''))
        db.session.commit()
    except Exception:
        db.session.rollback()


def notify_by_name(target_name, category, title, content='', link='', except_user_id=None):
    """按用户名/真实姓名查用户后通知（查不到或为自己时静默跳过）"""
    if not target_name:
        return
    from models import User
    try:
        target = User.query.filter(
            (User.username == target_name) | (User.realname == target_name)).first()
    except Exception:
        return
    if not target or (except_user_id is not None and target.id == except_user_id):
        return
    notify(target.id, category, title, content, link)


def notify_overdue_tasks():
    """逾期任务提醒（调度器每日调用）：通知任务指派工程师"""
    from datetime import datetime
    from models import InspectionTask, User
    from utils.constants import TASK_RUNNING, TASK_PENDING, TASK_REVIEWING

    today = datetime.now().date()
    rows = (InspectionTask.query
            .filter(InspectionTask.status.in_([TASK_PENDING, TASK_RUNNING, TASK_REVIEWING]))
            .filter(InspectionTask.planned_end.isnot(None))
            .all())
    overdue = [t for t in rows
               if t.planned_end and t.planned_end.date() < today and not t.actual_end]
    if not overdue:
        return 0
    by_user = {}
    for t in overdue:
        by_user.setdefault(t.assigned_to_user_id, []).append(t)
    sent = 0
    for uid, tasks in by_user.items():
        if uid is None:
            continue
        u = User.query.get(uid)
        if not u:
            continue
        titles = '、'.join(t.title for t in tasks[:3])
        more = f' 等 {len(tasks)} 项' if len(tasks) > 3 else ''
        notify(uid, 'inspection',
               f'{len(tasks)} 项巡检任务已逾期',
               f'{titles}{more}，请尽快处理',
               '/app/task-schedule')
        sent += 1
    return sent
