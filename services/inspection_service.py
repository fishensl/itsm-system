# -*- coding: utf-8 -*-
"""Inspection 巡检业务服务（V21：审核闭环版本化）

闭环：任务执行中 → 工程师上传报告（建 SubmissionVersion）→ 任务待审核
     → 管理员审核（意见挂版本）→ 通过=任务已完成 / 退回=任务回执行中可再传
任务↔记录 1:1：同一任务复用同一记录，每次上传追加新版本。
"""
import json
import os
from datetime import datetime
from flask import current_app
from models import db, Inspection, InspectionTask, User
from .base import ServiceError, transaction
from .submission_version_service import add_version, review_version, latest_pending_version
from .task_schedule_service import apply_task_status
from utils.constants import (REVIEW_PENDING, REVIEW_APPROVED, REVIEW_REJECTED,
                             TASK_PENDING, TASK_REVIEWING, TASK_RUNNING, TASK_DONE)


def _resolve_inspector(data, current_user_name):
    """V13: 从表单解析巡检人员，返回 (user_id, name, phone)。
    优先级：inspector_user_id (int) → inspector (字符串姓名) → current_user_name
    冻结快照写入 inspection 后，历史报告免疫 User 改名。
    """
    raw_uid = data.get('inspector_user_id')
    if raw_uid:
        try:
            uid = int(raw_uid)
        except (TypeError, ValueError):
            uid = None
        if uid:
            u = User.query.get(uid)
            if u:
                name = (u.realname or u.username or '').strip()
                return uid, name, (u.phone or '').strip()
    # fallback：仅有姓名字符串（兼容老表单/老草稿）
    name = (data.get('inspector') or current_user_name or '').strip()
    if name:
        u = User.query.filter_by(realname=name).first()
        if u:
            return u.id, name, (u.phone or '').strip()
    return None, name, ''


def inspection_completeness(i):
    """巡检记录资料完整性检查：返回 (complete, missing_fields)"""
    missing = []
    if not (i.title or '').strip():
        missing.append('标题')
    if not i.customer_id:
        missing.append('客户')
    if not i.inspector_user_id and not (i.inspector_name or '').strip():
        missing.append('工程师')
    if not (i.conclusion or '').strip():
        missing.append('结论')
    if not i.submitted_report:
        missing.append('现场报告')
    if not i.report_file:
        missing.append('正式报告')
    if i.review_status != '已通过':
        missing.append('审核通过')
    return not missing, missing


@transaction
def create_inspection(data, current_user_name):
    """新建巡检记录（V21：强制关联任务，任务↔记录 1:1）。

    - task_id 必填，任务必须存在且尚无记录；
    - 未显式传 customer_id / inspector 时从任务自动带出。
    """
    title = (data.get('title') or '').strip()
    if not title:
        raise ServiceError('巡检标题不能为空')
    task_id = data.get('task_id')
    try:
        task_id = int(task_id) if task_id else None
    except (TypeError, ValueError):
        task_id = None
    if not task_id:
        raise ServiceError('巡检记录必须关联巡检任务')
    task = InspectionTask.query.get(task_id)
    if not task:
        raise ServiceError('关联的巡检任务不存在')
    existing = Inspection.query.filter_by(task_id=task.id).first()
    if existing:
        raise ServiceError('该任务已存在巡检记录（任务↔记录 1:1），请直接在该记录上补充上传报告')

    inspection_date = data.get('inspection_date')
    if inspection_date:
        try:
            inspection_date = datetime.strptime(inspection_date, '%Y-%m-%d').date()
        except (ValueError, TypeError):
            inspection_date = None
    uid, name, phone = _resolve_inspector(data, current_user_name)
    if not uid and task.assigned_to_user_id:
        assignee = User.query.get(task.assigned_to_user_id)
        if assignee:
            uid = assignee.id
            name = (assignee.realname or assignee.username or '').strip()
            phone = (assignee.phone or '').strip()
    i = Inspection(
        title=title,
        customer_id=int(data['customer_id']) if data.get('customer_id') else task.customer_id,
        task_id=task.id,
        inspection_date=inspection_date or datetime.utcnow().date(),
        inspector=name,                  # 旧字段（向后兼容）
        inspector_user_id=uid,           # V13: 关联 User 用于追溯归属
        inspector_name=name,             # V13: 冻结快照
        inspector_phone=phone,           # V13: 冻结快照
        overall_status=data.get('overall_status', REVIEW_PENDING),
        location=data.get('location', ''),
        content_json=data.get('content_json', '[]'),
        field_values_json=data.get('field_values_json', '{}'),
        sections_json=data.get('sections_json', '{}'),
        skip_reasons_json=data.get('skip_reasons_json', '{}'),
    )
    db.session.add(i)
    db.session.flush()
    return i


@transaction
def update_inspection(inspection_id, data):
    """更新巡检 — V13: inspector_user_id 改变时刷新姓名/手机快照，
    未变更则保持原快照不动（避免无意改名污染历史）"""
    i = Inspection.query.get_or_404(inspection_id)
    i.title = (data.get('title') or i.title).strip()
    if data.get('customer_id'):
        i.customer_id = int(data['customer_id'])
    if data.get('task_id'):
        i.task_id = int(data['task_id'])
    if data.get('inspection_date'):
        try:
            i.inspection_date = datetime.strptime(data['inspection_date'], '%Y-%m-%d').date()
        except (ValueError, TypeError):
            pass
    # V13: 仅当提交的 inspector_user_id 与当前不同时刷新快照
    new_uid_raw = data.get('inspector_user_id')
    if new_uid_raw is not None and str(new_uid_raw) != '':
        try:
            new_uid = int(new_uid_raw)
        except (TypeError, ValueError):
            new_uid = None
        if new_uid and new_uid != i.inspector_user_id:
            u = User.query.get(new_uid)
            if u:
                name = (u.realname or u.username or '').strip()
                i.inspector_user_id = u.id
                i.inspector_name = name
                i.inspector_phone = (u.phone or '').strip()
                i.inspector = name
    elif data.get('inspector') and not i.inspector_user_id:
        # 老表单兜底：仅当还未关联 User 时允许修改字符串姓名
        i.inspector = data['inspector'].strip()
        i.inspector_name = i.inspector
    i.overall_status = data.get('overall_status', i.overall_status)
    if 'location' in data:
        i.location = data.get('location', i.location)
    if 'content_json' in data:
        i.content_json = data.get('content_json', i.content_json)
    if 'field_values_json' in data:
        i.field_values_json = data.get('field_values_json', i.field_values_json)
    if 'sections_json' in data:
        i.sections_json = data.get('sections_json', i.sections_json)
    if 'skip_reasons_json' in data:
        i.skip_reasons_json = data.get('skip_reasons_json', i.skip_reasons_json)
    return i


def _task_from_inspection(i):
    return i.task_rel


def _sync_task_to_reviewing(i, current_user_id=None):
    """记录提交审核 → 关联任务同步为「待审核」。

    - 任务「执行中」→「待审核」；
    - 任务「待执行」→ 自动开始（写 actual_start）→「待审核」。
    """
    task = _task_from_inspection(i)
    if not task:
        return None
    if task.status == TASK_RUNNING:
        apply_task_status(task, TASK_REVIEWING)
    elif task.status == TASK_PENDING:
        task.status = TASK_RUNNING
        task.actual_start = task.actual_start or datetime.utcnow()
        apply_task_status(task, TASK_REVIEWING)
    return task


def _revert_task_to_running(i):
    """记录被退回 → 关联任务回「执行中」（若任务处于待审核）。"""
    task = _task_from_inspection(i)
    if task and task.status == TASK_REVIEWING:
        task.status = TASK_RUNNING
        task.actual_start = task.actual_start or datetime.utcnow()


@transaction
def upload_report_for_task(task_id, report_path, conclusion, current_user_id,
                           current_user_name, submit_review=True, force=False):
    """工程师从任务上传现场报告 → 自动生成/复用巡检记录并提交审核。

    规则：
    - 任务必须存在且处于「执行中」（待审核时不可重复上传）；
    - 上传者必须是任务指派者本人；force=True 时跳过归属校验（管理员代传）；
    - 任务已有「待审核」版本时拒绝重复上传（先等审核）；
    - 任务已有「已退回」记录时允许再次上传（追加新版本，历史留档）；
    - 创建记录后任务「执行中 → 待审核」。
    返回 (inspection, version)。
    """
    task = InspectionTask.query.get_or_404(task_id)
    if task.status not in (TASK_RUNNING, TASK_REVIEWING, TASK_PENDING):
        raise ServiceError('任务状态「%s」不允许上传报告（仅执行中/待审核中的任务可上传）' % task.status)

    if not force and task.assigned_to_user_id and current_user_id \
            and int(task.assigned_to_user_id) != int(current_user_id):
        raise ServiceError('只有该任务指派工程师或管理员可以上传报告')

    inspection = Inspection.query.filter_by(task_id=task.id).first()
    if inspection:
        if inspection.review_status == REVIEW_PENDING:
            raise ServiceError('该任务已有「待审核」巡检记录，请等待审核结果后再上传')
        pending = latest_pending_version('inspection', inspection.id)
        if pending and pending.review_status == REVIEW_PENDING:
            raise ServiceError('该任务已有「待审核」版本（版本 %d），请等待审核结果后再上传' % pending.version_no)
    else:
        if task.status not in (TASK_RUNNING, TASK_PENDING):
            raise ServiceError('任务「%s」状态不能创建巡检记录' % task.status)
        inspection = Inspection(
            title=task.title,
            customer_id=task.customer_id,
            task_id=task.id,
            inspection_date=datetime.utcnow().date(),
            inspector_name=current_user_name,
            inspector=current_user_name,
            inspector_user_id=current_user_id,
            overall_status=REVIEW_PENDING,
            review_status=REVIEW_PENDING,
        )
        db.session.add(inspection)
        db.session.flush()

    version = add_version(
        'inspection', inspection.id,
        report_file=report_path,
        content={'conclusion': conclusion or ''},
        submitted_by_user_id=current_user_id,
        review_status=REVIEW_PENDING if submit_review else '',
    )
    inspection.submitted_report = report_path
    inspection.review_status = REVIEW_PENDING
    inspection.overall_status = REVIEW_PENDING
    inspection.conclusion = conclusion or ''
    if submit_review:
        _sync_task_to_reviewing(inspection)
    return inspection, version


@transaction
def submit_for_review(inspection_id, current_user_name):
    """提交审核 — V21: review_status='待审核' + 任务同步「待审核」"""
    from utils.json_fields import parse_json
    i = Inspection.query.get_or_404(inspection_id)
    if i.review_status == REVIEW_PENDING:
        raise ServiceError('该记录已处于待审核，请等待审核结果')
    has_content = bool(parse_json(i.content_json, [], 'inspection.content_json'))
    if not i.submitted_report and not has_content:
        raise ServiceError('请先上传巡检报告再提交审核')
    i.overall_status = REVIEW_PENDING
    i.review_status = REVIEW_PENDING
    _sync_task_to_reviewing(i)
    return i


@transaction
def review_inspection(inspection_id, approved, current_user_name, remark=''):
    """审核巡检 — V21: 审核结果/意见写回最新待审核版本 + 任务联动。

    审核通过 (approved=True):
        - review_status = '已通过'，overall_status = '正常'
        - 自动生成正式 Word 报告
        - 关联任务「待审核 → 已完成」（写 actual_end）
    审核退回 (approved=False):
        - review_status = '已退回'，overall_status = '异常'（审核意见挂版本）
        - 关联任务「待审核 → 执行中」，工程师可修改后重新上传
    """
    from models import User as _User
    i = Inspection.query.get_or_404(inspection_id)
    if i.review_status != REVIEW_PENDING:
        raise ServiceError('该记录不处于待审核状态，无法审核')

    reviewer = _User.query.filter_by(username=current_user_name).first()

    pending = latest_pending_version('inspection', i.id)
    if pending:
        review_version(pending.id, approved,
                       reviewer_user_id=reviewer.id if reviewer else None, comment=remark)

    i.review_status = REVIEW_APPROVED if approved else REVIEW_REJECTED
    i.overall_status = '正常' if approved else '异常'
    i.reviewed_by = reviewer.id if reviewer else None
    i.reviewed_at = datetime.utcnow()
    if remark:
        i.review_comment = remark

    task = _task_from_inspection(i)
    if approved:
        if task and task.status == TASK_REVIEWING:
            apply_task_status(task, TASK_DONE)
        try:
            _generate_report_for_inspection(i)
        except Exception as e:
            # 报告生成失败不阻塞审核通过，仅记日志
            try:
                current_app.logger.exception('生成巡检报告失败 inspection_id=%s: %s', i.id, e)
            except Exception:
                pass
    else:
        _revert_task_to_running(i)
    return i


def _generate_report_for_inspection(inspection):
    """V11: 调用 generate_inspection_report_v4 生成 Word 文档（函数内部已保存到 reports/ 目录），把文件名写入 inspection.report_file"""
    from utils.report_generator import generate_inspection_report_v4
    from models import Customer

    cust = Customer.query.get(inspection.customer_id) if inspection.customer_id else None
    customer_name = cust.name if cust else '未知客户'

    # 解析 sections_json
    sections = {}
    try:
        if inspection.sections_json:
            sections = json.loads(inspection.sections_json) or {}
    except Exception:
        sections = {}

    # 调用生成器，它会保存到 reports/<filename>.docx 并返回完整路径
    fpath = generate_inspection_report_v4(inspection, customer_name, device_results=None, sections=sections)
    if not fpath:
        return None
    fname = os.path.basename(fpath) if isinstance(fpath, str) else None
    if fname:
        inspection.report_file = fname
    return fname


@transaction
def delete_inspection(inspection_id):
    """删除巡检记录；关联任务仍「待审核」且无其他待审核记录时任务回「执行中」。"""
    from models import SubmissionVersion
    i = Inspection.query.get_or_404(inspection_id)
    task = _task_from_inspection(i)
    if task and task.status == TASK_REVIEWING:
        task.status = TASK_RUNNING
    SubmissionVersion.query.filter_by(entity_type='inspection', entity_id=i.id).delete()
    db.session.delete(i)
