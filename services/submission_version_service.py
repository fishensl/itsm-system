# -*- coding: utf-8 -*-
"""提交版本服务 — 巡检记录 / 工单审核闭环的版本化管理

每次"上传报告+提交审核" = add_version() 追加一条 SubmissionVersion；
审核 = review_version() 把审核结果/意见写回对应版本。
全部版本永久保留，单条记录即可复查完整提交与审核历史。
"""
import json
import os
from datetime import datetime

from models import db, SubmissionVersion, SubmissionAsset


def add_asset(version_id, asset_type, file_path='', file_name='', device_id=None,
              content_text='', target_id=None, skip_reason=''):
    """为版本追加一条提交资料记录（含必传项豁免 skip_reason）。"""
    a = SubmissionAsset(
        version_id=version_id,
        asset_type=asset_type,
        file_path=file_path or '',
        file_name=file_name or (file_path or '').split('/')[-1] or '',
        device_id=device_id,
        content_text=content_text or '',
        target_id=target_id,
        skip_reason=skip_reason or '',
    )
    db.session.add(a)
    db.session.flush()
    return a


def add_version(entity_type, entity_id, report_file='', content=None,
                submitted_by_user_id=None, review_status='待审核'):
    """追加一个提交版本（version_no 自动 +1）。返回 SubmissionVersion 实例。"""
    entity_type = entity_type if entity_type in ('inspection', 'ticket') else 'inspection'
    latest = SubmissionVersion.query \
        .filter_by(entity_type=entity_type, entity_id=entity_id) \
        .order_by(SubmissionVersion.version_no.desc()).first()
    version_no = (latest.version_no + 1) if latest else 1
    v = SubmissionVersion(
        entity_type=entity_type,
        entity_id=entity_id,
        version_no=version_no,
        report_file=report_file or '',
        content_json=json.dumps(content or {}, ensure_ascii=False),
        submitted_by=submitted_by_user_id,
        submitted_at=datetime.utcnow(),
        review_status=review_status or '',
    )
    db.session.add(v)
    db.session.flush()
    return v


def review_version(version_id, approved, reviewer_user_id=None, comment='', requirements='', checklist=None):
    """审核指定版本：写回审核结果/审核人/时间/意见/修改要求/检查项勾选。返回该版本实例。"""
    from utils.constants import REVIEW_APPROVED, REVIEW_REJECTED
    v = SubmissionVersion.query.get_or_404(version_id)
    v.review_status = REVIEW_APPROVED if approved else REVIEW_REJECTED
    v.reviewed_by = reviewer_user_id
    v.reviewed_at = datetime.utcnow()
    if comment:
        v.review_comment = comment
    if requirements:
        v.revision_requirements = requirements
    if checklist is not None:
        v.review_checklist_json = json.dumps(checklist or {}, ensure_ascii=False)
    return v


def list_versions(entity_type, entity_id):
    """按版本号升序返回全部版本（含提交人/审核人姓名 + 资料明细）。"""
    rows = SubmissionVersion.query \
        .filter_by(entity_type=entity_type, entity_id=entity_id) \
        .order_by(SubmissionVersion.version_no.asc()).all()
    payloads = [_version_payload(v) for v in rows]
    _attach_assets(payloads)
    return payloads


def _attach_assets(payloads):
    """批量预取各版本的资料明细（防 N+1）"""
    if not payloads:
        return
    version_ids = [p['id'] for p in payloads]
    rows = SubmissionAsset.query \
        .filter(SubmissionAsset.version_id.in_(version_ids)) \
        .order_by(SubmissionAsset.id.asc()).all()
    by_version = {}
    for a in rows:
        by_version.setdefault(a.version_id, []).append(a)
    for p in payloads:
        p['assets'] = [_asset_payload(a) for a in by_version.get(p['id'], [])]


def _asset_payload(a):
    device_name = ''
    if a.device_id:
        dev = a.device_rel
        if dev:
            device_name = dev.device_name or ''
    return {
        'id': a.id,
        'asset_type': a.asset_type or '',
        'file_path': a.file_path or '',
        'file_name': a.file_name or '',
        'device_id': a.device_id,
        'device_name': device_name,
        'has_content': bool(a.content_text),
        'content_text': a.content_text or '',
        'target_id': a.target_id,
        'skip_reason': a.skip_reason or '',
    }


def latest_pending_version(entity_type, entity_id):
    """返回当前待审核的最新版本（无则 None）。"""
    return SubmissionVersion.query \
        .filter_by(entity_type=entity_type, entity_id=entity_id, review_status='待审核') \
        .order_by(SubmissionVersion.version_no.desc()).first()


def report_display_name(entity_type, customer_name, task_title, storage_name, version_no=None, approved=False):
    """报告可读文件名：{任务标题}报告{NN}.{ext}，审核通过（定稿）去掉序号。

    - 任务标题未含客户名时拼接客户前缀（如「鄱阳县水利局5月例行巡检报告01.docx」）
    - 审核中/已退回：带两位版本序号（01/02/...）；审核通过（定稿）：无序号
    - 存储名仅用于取扩展名（存储名可能是清洗后的短名/不可读）
    返回纯文件名（不含路径）。
    """
    ext = os.path.splitext(storage_name or '')[1]
    base = task_title or ''
    if customer_name and base and not base.startswith(customer_name):
        base = f'{customer_name}{base}'
    label = '处理报告' if entity_type == 'ticket' else '报告'
    name = f'{base}{label}'
    if not approved and version_no:
        name += f'{int(version_no):02d}'
    if ext:
        name += ext
    if len(name) > 100:
        name = name[:100 - len(ext)] + ext
    return name or storage_name or '报告'


def version_context(entity_type, entity_id):
    """查询版本所属实体的客户名/标题（inspection→task→customer；ticket→customer）"""
    customer_name = ''
    title = ''
    if entity_type == 'ticket':
        from models import Ticket
        t = Ticket.query.get(entity_id)
        if t:
            title = t.title or ''
            customer_name = t.customer_rel.name if t.customer_rel else ''
    else:
        from models import Inspection
        i = Inspection.query.get(entity_id)
        if i:
            title = i.title or ''
            task = i.task_rel
            if task:
                title = task.title or title
                customer_name = task.customer_rel.name if task.customer_rel else ''
            else:
                customer_name = i.customer_rel.name if i.customer_rel else ''
    return customer_name, title


def _version_payload(v):
    from utils.json_fields import parse_json
    submitter = v.submitter_rel
    reviewer = v.reviewer_rel
    storage_name = (v.report_file or '').split('/')[-1] or ''
    customer_name, title = version_context(v.entity_type, v.entity_id)
    approved = v.review_status == '已通过'
    return {
        'id': v.id,
        'version_no': v.version_no,
        'report_file': bool(v.report_file),
        'report_name': report_display_name(v.entity_type, customer_name, title,
                                           storage_name, v.version_no, approved),
        'content': parse_json(v.content_json, {}, 'submission_versions.content_json'),
        'submitted_by_name': (submitter.realname or submitter.username) if submitter else '',
        'submitted_at': v.submitted_at.strftime('%Y-%m-%d %H:%M') if v.submitted_at else '',
        'review_status': v.review_status or '',
        'reviewed_by_name': (reviewer.realname or reviewer.username) if reviewer else '',
        'reviewed_at': v.reviewed_at.strftime('%Y-%m-%d %H:%M') if v.reviewed_at else '',
        'review_comment': v.review_comment or '',
        'revision_requirements': v.revision_requirements or '',
        'checklist': parse_json(v.review_checklist_json, {}, 'submission_versions.review_checklist_json'),
    }
