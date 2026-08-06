# -*- coding: utf-8 -*-
"""报告文件：删除/下载（报告中心列表已由 Vue SPA /api/reports 接管）"""
import os
from flask import request, redirect, flash, send_from_directory, current_app, abort
from flask_login import login_required, current_user
from models import (Inspection, Ticket)
from utils.permission import require_permission
from blueprints.ops import ops_bp


# ============================ 报告 ============================
REPORTS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'reports')


def _safe_report_path(filename):
    """报告文件名安全校验：防路径穿越 + 扩展名白名单。返回绝对路径或 None。"""
    if not filename or not filename.lower().endswith(('.docx', '.pdf')):
        return None
    full = os.path.realpath(os.path.join(REPORTS_DIR, filename))
    base = os.path.realpath(REPORTS_DIR)
    if full.startswith(base + os.sep) and os.path.isfile(full):
        return full
    return None


@ops_bp.route('/reports/delete/<path:filename>', methods=['POST'])
@login_required
@require_permission('report:delete')
def report_delete(filename):
    full = _safe_report_path(filename)
    if full is None:
        flash('非法的报告文件名', 'danger')
        current_app.logger.warning(
            '报告删除被拒绝: 用户[%s] 文件名[%s], IP=%s',
            current_user.username, filename, request.remote_addr)
        return redirect('/app/reports')
    os.remove(full)
    # 回清引用：报告被删后详情页下载入口应随之消失（避免 404 孤儿引用）
    fname = os.path.basename(full)
    Inspection.query.filter_by(report_file=fname).update({'report_file': ''})
    Ticket.query.filter_by(report_file=fname).update({'report_file': ''})
    from models import db
    db.session.commit()
    from blueprints.vue_api_sys import audit_log  # noqa: E402
    audit_log('report:delete', 'report', None, f'删除报告文件 {fname}')
    current_app.logger.info(
        '报告删除审计: 用户[%s] 删除报告[%s], IP=%s',
        current_user.username, os.path.basename(full), request.remote_addr)
    flash('已删除', 'success')
    return redirect('/app/reports')


@ops_bp.route('/reports/<path:filename>')
@login_required
@require_permission('report:view')
def report_download(filename):
    full = _safe_report_path(filename)
    if full is None:
        abort(404)
    return send_from_directory(os.path.dirname(full), os.path.basename(full), as_attachment=True)
