# -*- coding: utf-8 -*-
"""Inspection 巡检业务服务"""
import json
import os
from datetime import datetime
from flask import current_app
from models import db, Inspection, User
from .base import ServiceError, transaction


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


@transaction
def create_inspection(data, current_user_name):
    """新建巡检记录"""
    title = (data.get('title') or '').strip()
    if not title:
        raise ServiceError('巡检标题不能为空')
    inspection_date = data.get('inspection_date')
    if inspection_date:
        try:
            inspection_date = datetime.strptime(inspection_date, '%Y-%m-%d').date()
        except (ValueError, TypeError):
            inspection_date = None
    uid, name, phone = _resolve_inspector(data, current_user_name)
    i = Inspection(
        title=title,
        customer_id=int(data['customer_id']) if data.get('customer_id') else None,
        task_id=int(data['task_id']) if data.get('task_id') else None,
        inspection_date=inspection_date or datetime.utcnow().date(),
        inspector=name,                  # 旧字段（向后兼容）
        inspector_user_id=uid,           # V13: 关联 User 用于追溯归属
        inspector_name=name,             # V13: 冻结快照
        inspector_phone=phone,           # V13: 冻结快照
        overall_status=data.get('overall_status', '正常'),
        location=data.get('location', ''),
        content_json=data.get('content_json', '[]'),
        field_values_json=data.get('field_values_json', '{}'),
        sections_json=data.get('sections_json', '{}'),
        skip_reasons_json=data.get('skip_reasons_json', '{}'),
    )
    db.session.add(i)
    return i


@transaction
def update_inspection(inspection_id, data):
    """更新巡检 — V13: inspector_user_id 改变时刷新姓名/手机快照，
    未变更则保持原快照不动（避免无意改名污染历史）"""
    i = Inspection.query.get_or_404(inspection_id)
    i.title = (data.get('title') or i.title).strip()
    i.customer_id = int(data['customer_id']) if data.get('customer_id') else i.customer_id
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


@transaction
def submit_for_review(inspection_id, current_user_name):
    """提交审核 — V11: 同时更新 review_status='待审核'"""
    from utils.constants import REVIEW_PENDING
    i = Inspection.query.get_or_404(inspection_id)
    i.overall_status = REVIEW_PENDING
    i.review_status = REVIEW_PENDING
    return i


@transaction
def review_inspection(inspection_id, approved, current_user_name, remark=''):
    """审核巡检 — V11: 通过时自动生成 Word 报告

    审核通过 (approved=True):
        - review_status = '已通过'
        - overall_status = '正常'
        - 自动调用 generate_inspection_report_v4() 生成 Word
        - 报告路径写入 Inspection.report_file
    审核退回 (approved=False):
        - review_status = '已退回'
        - overall_status = '异常'
        - 不生成报告，工程师可修改后重新提交
    """
    from models import User
    from utils.constants import REVIEW_APPROVED, REVIEW_REJECTED
    i = Inspection.query.get_or_404(inspection_id)

    # 找审核人 user 对象
    reviewer = User.query.filter_by(username=current_user_name).first()

    i.review_status = REVIEW_APPROVED if approved else REVIEW_REJECTED
    i.overall_status = '正常' if approved else '异常'
    i.reviewed_by = reviewer.id if reviewer else None
    i.reviewed_at = datetime.utcnow()
    if remark:
        i.review_comment = remark

    # 审核通过 → 自动生成 Word 报告
    if approved:
        try:
            _generate_report_for_inspection(i)
        except Exception as e:
            # 报告生成失败不阻塞审核通过，仅记日志
            try:
                current_app.logger.exception('生成巡检报告失败 inspection_id=%s: %s', i.id, e)
            except Exception:
                pass

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
    i = Inspection.query.get_or_404(inspection_id)
    db.session.delete(i)
