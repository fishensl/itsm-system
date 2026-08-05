# -*- coding: utf-8 -*-
"""提交版本服务 — 巡检记录 / 工单审核闭环的版本化管理

每次"上传报告+提交审核" = add_version() 追加一条 SubmissionVersion；
审核 = review_version() 把审核结果/意见写回对应版本。
全部版本永久保留，单条记录即可复查完整提交与审核历史。
"""
import json
from datetime import datetime

from models import db, SubmissionVersion


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


def review_version(version_id, approved, reviewer_user_id=None, comment=''):
    """审核指定版本：写回审核结果/审核人/时间/意见。返回该版本实例。"""
    from utils.constants import REVIEW_APPROVED, REVIEW_REJECTED
    v = SubmissionVersion.query.get_or_404(version_id)
    v.review_status = REVIEW_APPROVED if approved else REVIEW_REJECTED
    v.reviewed_by = reviewer_user_id
    v.reviewed_at = datetime.utcnow()
    if comment:
        v.review_comment = comment
    return v


def list_versions(entity_type, entity_id):
    """按版本号升序返回全部版本（含提交人/审核人姓名）。"""
    rows = SubmissionVersion.query \
        .filter_by(entity_type=entity_type, entity_id=entity_id) \
        .order_by(SubmissionVersion.version_no.asc()).all()
    return [_version_payload(v) for v in rows]


def latest_pending_version(entity_type, entity_id):
    """返回当前待审核的最新版本（无则 None）。"""
    return SubmissionVersion.query \
        .filter_by(entity_type=entity_type, entity_id=entity_id, review_status='待审核') \
        .order_by(SubmissionVersion.version_no.desc()).first()


def _version_payload(v):
    from utils.json_fields import parse_json
    submitter = v.submitter_rel
    reviewer = v.reviewer_rel
    return {
        'id': v.id,
        'version_no': v.version_no,
        'report_file': bool(v.report_file),
        'report_name': (v.report_file or '').split('/')[-1] or '',
        'content': parse_json(v.content_json, {}, 'submission_versions.content_json'),
        'submitted_by_name': (submitter.realname or submitter.username) if submitter else '',
        'submitted_at': v.submitted_at.strftime('%Y-%m-%d %H:%M') if v.submitted_at else '',
        'review_status': v.review_status or '',
        'reviewed_by_name': (reviewer.realname or reviewer.username) if reviewer else '',
        'reviewed_at': v.reviewed_at.strftime('%Y-%m-%d %H:%M') if v.reviewed_at else '',
        'review_comment': v.review_comment or '',
    }
