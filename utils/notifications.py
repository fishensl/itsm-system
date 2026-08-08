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


def _admin_user_ids(except_user_id=None):
    """全部 admin 用户 id（role 或 role_codes 含 admin）"""
    from models import User
    users = User.query.filter_by(is_active=True).all()
    ids = []
    for u in users:
        if u.has_role('admin') and u.id != except_user_id:
            ids.append(u.id)
    return ids


def notify_review_submitted(department_id, category, title, content='', link='',
                            except_user_id=None):
    """提交审核通知：提交人所在部门的负责人（Department.head_id）+ 全部 admin。

    用于工单提交审核 / 巡检提交审核 / 任务上传全套资料三处，失败静默不阻断主流程。
    """
    from models import Department
    targets = []
    if department_id:
        dept = Department.query.get(department_id)
        if dept and dept.head_id and dept.head_id != except_user_id:
            targets.append(dept.head_id)
    targets.extend(_admin_user_ids(except_user_id))
    for uid in dict.fromkeys(targets):
        notify(uid, category, title, content, link)


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


def notify_review_timeout():
    """巡检/工单审核超时提醒（调度器每日调用）。

    查 SubmissionVersion.review_status='待审核' 且超过 REVIEW_TIMEOUT_DAYS 天未审的
    记录，通知提交人部门主管 + 全部 admin（复用 notify_review_submitted 目标集）。
    返回通知数；失败不阻断。
    """
    from datetime import datetime, timedelta
    from models import SubmissionVersion, User
    from utils.constants import REVIEW_TIMEOUT_DAYS

    try:
        cutoff = datetime.utcnow() - timedelta(days=REVIEW_TIMEOUT_DAYS)
        # 取最早一条待审核版本时间（version 表有 created_at），聚合按 entity 去重
        rows = (SubmissionVersion.query
                .filter(SubmissionVersion.review_status == '待审核',
                        SubmissionVersion.created_at.isnot(None),
                        SubmissionVersion.created_at < cutoff)
                .order_by(SubmissionVersion.id)
                .all())
        if not rows:
            return 0
        # 按 entity 去重（同一工单/巡检多次退回重提只提醒一次），并找提交人部门
        seen = set()
        sent = 0
        for v in rows:
            key = (v.entity_type, v.entity_id)
            if key in seen:
                continue
            seen.add(key)
            submitter = None
            if v.submitted_by:
                submitter = User.query.get(v.submitted_by)
            dept_id = submitter.department_id if submitter else None
            label = '巡检' if v.entity_type == 'inspection' else '工单'
            # 通知提交人部门主管 + admin（except 提交人本人）
            notify_review_submitted(
                dept_id, 'review',
                f'{label} #{v.entity_id} 审核超时',
                f'已超过 {REVIEW_TIMEOUT_DAYS} 天未审核，请及时处理',
                f'/app/{v.entity_type}s/{v.entity_id}' if v.entity_type == 'inspection'
                else f'/app/tickets/{v.entity_id}',
                except_user_id=submitter.id if submitter else None)
            sent += 1
        return sent
    except Exception:
        from flask import current_app
        try:
            current_app.logger.exception('审核超时提醒失败')
        except Exception:
            pass
        return 0
