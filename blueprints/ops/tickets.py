# -*- coding: utf-8 -*-
"""工单导出端点（SSR CRUD 与状态机动作已由 Vue SPA /api/* 接管，仅保留导出）"""
import os
from flask import request, redirect, flash
from flask_login import login_required
from models import (Ticket, Customer)
from utils.permission import require_permission
from blueprints.ops import ops_bp


# ============== V21 工单导出（按客户 + 自定义时间段） ==============
def _ticket_export_filter(args):
    """解析导出筛选参数 → (query, customer_map)"""
    from datetime import date as _date
    q = Ticket.query
    customer_id = args.get('customer_id', type=int)
    date_from = args.get('date_from') or ''
    date_to = args.get('date_to') or ''
    if customer_id:
        q = q.filter(Ticket.customer_id == customer_id)
    if date_from:
        try:
            q = q.filter(Ticket.created_at >= _date.fromisoformat(date_from))
        except ValueError:
            pass
    if date_to:
        try:
            q = q.filter(Ticket.created_at <= _date.fromisoformat(date_to))
        except ValueError:
            pass
    return q.order_by(Ticket.id.desc()).all()


def _ticket_export_rows(tickets):
    """工单导出行 + 收集报告文件列表 [(完整路径, zip内名)]"""
    from models import SubmissionVersion
    customer_map = {c.id: c.name for c in Customer.query.all()}
    headers = ['单号', '标题', '客户', '状态', '优先级', '处理人', '创建时间',
               '诊断', '方案', '处理报告', '审核状态', '审核意见', '资料完整']
    rows = []
    files = []
    for t in tickets:
        cust = customer_map.get(t.customer_id, '-')
        versions = SubmissionVersion.query \
            .filter_by(entity_type='ticket', entity_id=t.id) \
            .order_by(SubmissionVersion.version_no.asc()).all()
        for v in versions:
            if v.report_file:
                full = os.path.realpath(os.path.join('static', v.report_file))
                if os.path.isfile(full):
                    fname = os.path.basename(v.report_file)
                    files.append((full, f'{cust}/工单{t.number}/v{v.version_no}_{fname}'))
        rows.append([
            t.number, t.title, cust, t.status, t.priority or '', t.assigned_to or '',
            t.created_at.strftime('%Y-%m-%d %H:%M') if t.created_at else '',
            t.diagnosis or '', t.solution or '',
            '有' if t.report_file else '无',
            (t.audit_status or '') + (f'（{t.audit_comment}）' if t.audit_comment else ''),
            '完整' if not [x for x in [t.assigned_to, t.diagnosis, t.solution, t.report_file,
                                       t.audit_status] if not x] else '缺失',
        ])
    return headers, rows, files


@ops_bp.route('/tickets/export')
@login_required
@require_permission('ticket:view')
def ticket_export():
    """工单记录导出 Excel（?customer_id=&date_from=&date_to=）"""
    from datetime import date as _date
    from utils.excel_export import export_xlsx, send_temp_export
    tickets = _ticket_export_filter(request.args)
    headers, rows, _files = _ticket_export_rows(tickets)
    path, download_name = export_xlsx(
        headers, rows, f'工单导出_{_date.today().isoformat()}.xlsx', sheet_name='工单记录')
    return send_temp_export(path, download_name)


@ops_bp.route('/tickets/reports-zip')
@login_required
@require_permission('ticket:view')
def ticket_reports_zip():
    """工单记录+处理报告打包下载（按客户/时间段筛选）"""
    from datetime import date as _date
    from utils.excel_export import export_xlsx, send_temp_export
    from utils.report_zip import build_records_zip
    tickets = _ticket_export_filter(request.args)
    headers, rows, files = _ticket_export_rows(tickets)
    if not rows:
        flash('当前筛选条件下没有可导出的工单记录', 'warning')
        return redirect(request.referrer or '/app/tickets')
    excel_path, _ = export_xlsx(headers, rows, '工单明细.xlsx', sheet_name='工单记录')
    zip_path = build_records_zip(excel_path, files, '工单报告包')
    return send_temp_export(
        zip_path, f'工单报告包_{_date.today().isoformat()}.zip', cleanup_paths=(excel_path,))
