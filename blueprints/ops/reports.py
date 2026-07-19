# -*- coding: utf-8 -*-
"""报告中心：客户分桶 × 巡检/故障/工单/文件 四 tab + 删除/下载"""
import os
from datetime import datetime, timedelta
from flask import (render_template, request, redirect, url_for,
                   flash, send_from_directory, current_app, abort)
from flask_login import login_required, current_user
from sqlalchemy.orm import joinedload
from models import (Inspection, Fault, Ticket,
                    Customer)
from utils.permission import require_permission
from utils.customer_task_generator import QUARTER_CN
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

@ops_bp.route('/reports')
@login_required
@require_permission('report:view')
def report_list():
    """报告管理：客户优先 + 类型徽章，tab 控制展示哪些类型"""
    scope = request.args.get('scope', 'all')               # all/mine
    date_from = request.args.get('date_from', '')
    date_to = request.args.get('date_to', '')
    customer_id = request.args.get('customer_id', type=int)
    # 统一 tab：'all' / 'inspection' / 'fault' / 'ticket' / 'file'，单变量控制高亮
    valid_tabs = ('all', 'inspection', 'fault', 'ticket', 'file')
    tab = request.args.get('tab', 'all')
    if tab not in valid_tabs:
        tab = 'all'

    me = current_user.realname or current_user.username

    # 性能：首次进入（无任何过滤条件）默认只看近 12 个月，避免三表全量扫描；
    # 用户显式选择日期/客户后按条件查询（客户传 customer_id=0 视为全部）
    default_window = False
    if not date_from and not date_to and not customer_id:
        date_from = (datetime.now().date() - timedelta(days=365)).isoformat()
        default_window = True

    # --- 顶部"客户"下拉（预加载所有客户） ---
    customers_index = {c.id: c for c in Customer.query.order_by(Customer.name).all()}

    def _ensure_cust(cid, cname, unassigned):
        """获取或初始化一个客户桶"""
        if cid not in data:
            data[cid] = {
                'id': cid,
                'name': cname,
                'is_unassigned': unassigned,
                'counts': {'inspection': 0, 'fault': 0, 'ticket': 0, 'file': 0},
                'types': {
                    'inspection': {'subs': {}},
                    'fault':      {'subs': {}},
                    'ticket':     {'subs': {}},
                    'file':       {'files': []},
                }
            }
        return data[cid]

    def _push_record(cid, cname, rt, sub_key, sub_label, item, unassigned=False):
        bucket = _ensure_cust(cid, cname, unassigned)
        bucket['counts'][rt] += 1
        if rt == 'file':
            bucket['types']['file']['files'].append(item)
        else:
            # 键名 items_list 与 reports/list.html 渲染契约一致（曾用 items 导致明细行不渲染）
            sub = bucket['types'][rt]['subs'].setdefault(
                sub_key, {'label': sub_label, 'items_list': []}
            )
            sub['items_list'].append(item)

    data = {}  # customer_id | None -> payload

    # --- 巡检：按季度子分组 ---
    if tab in ('all', 'inspection'):
        q = Inspection.query.options(joinedload(Inspection.customer_rel))
        if date_from:
            q = q.filter(Inspection.inspection_date >= date_from)
        if date_to:
            q = q.filter(Inspection.inspection_date <= date_to)
        if customer_id:
            q = q.filter(Inspection.customer_id == customer_id)
        if scope == 'mine':
            q = q.filter(Inspection.inspector == me)
        for i in q.order_by(Inspection.inspection_date.desc(), Inspection.id.desc()).all():
            cust = i.customer_rel
            if cust is None:
                _push_record(None, '未关联客户', 'inspection', 'unknown', '未知时间', i, unassigned=True)
            else:
                if i.inspection_date:
                    qnum = (i.inspection_date.month - 1) // 3 + 1
                    sub_key = f'{i.inspection_date.year}-Q{qnum}'
                    sub_label = f'{i.inspection_date.year}年第{QUARTER_CN[qnum]}季度'
                else:
                    sub_key, sub_label = 'unknown', '未知时间'
                _push_record(cust.id, cust.name, 'inspection', sub_key, sub_label, i)

    # --- 故障：按一级分类子分组 ---
    if tab in ('all', 'fault'):
        q = Fault.query.options(joinedload(Fault.customer_rel))
        if date_from:
            q = q.filter(Fault.fault_time >= date_from)
        if date_to:
            q = q.filter(Fault.fault_time <= date_to)
        if customer_id:
            q = q.filter(Fault.customer_id == customer_id)
        if scope == 'mine':
            q = q.filter(Fault.handler == me)
        for f in q.order_by(Fault.fault_time.desc(), Fault.id.desc()).all():
            cust = f.customer_rel
            label_key = f.fault_category_level1 or '未分类'
            if cust is None:
                _push_record(None, '未关联客户', 'fault', label_key, label_key, f, unassigned=True)
            else:
                _push_record(cust.id, cust.name, 'fault', label_key, label_key, f)

    # --- 工单：按优先级子分组 ---
    if tab in ('all', 'ticket'):
        q = Ticket.query.options(joinedload(Ticket.customer_rel))
        if date_from:
            q = q.filter(Ticket.created_at >= date_from)
        if date_to:
            q = q.filter(Ticket.created_at <= date_to)
        if customer_id:
            q = q.filter(Ticket.customer_id == customer_id)
        if scope == 'mine':
            q = q.filter((Ticket.assigned_to == me) | (Ticket.created_by == me))
        for t in q.order_by(Ticket.created_at.desc(), Ticket.id.desc()).all():
            cust = t.customer_rel
            label_key = t.priority or '普通'
            if cust is None:
                _push_record(None, '未关联客户', 'ticket', label_key, label_key, t, unassigned=True)
            else:
                _push_record(cust.id, cust.name, 'ticket', label_key, label_key, t)

    # --- 文件式报告：扫描 REPORTS_DIR，反查 report_file 归属 ---
    if tab in ('all', 'file') and os.path.exists(REPORTS_DIR):
        # 反查索引：兼容多种 report_file 存储形态
        def _normkey(p):
            if not p:
                return ''
            return os.path.normcase(os.path.normpath(p))

        file_to_record = {}
        for Mdl in (Inspection, Fault, Ticket):
            # 只取有报告文件的记录（原实现三表全量扫描），并预加载 customer_rel
            for rec in Mdl.query.options(joinedload(Mdl.customer_rel)).filter(
                    Mdl.report_file.isnot(None), Mdl.report_file != '').all():
                v = (rec.report_file or '').strip()
                if not v:
                    continue
                cands = {
                    v,
                    os.path.basename(v),
                    _normkey(v),
                    _normkey(os.path.basename(v)),
                    _normkey(os.path.join('reports', v)),
                }
                for c in cands:
                    if c and c not in file_to_record:
                        file_to_record[c] = rec

        for fname in sorted(os.listdir(REPORTS_DIR), reverse=True):
            full = os.path.join(REPORTS_DIR, fname)
            if not os.path.isfile(full):
                continue
            ftype = '巡检' if '巡检' in fname else ('故障' if '故障' in fname else '其他')
            ftype_label = ftype + '报告' if ftype != '其他' else '其他'
            rec = (file_to_record.get(_normkey(full))
                   or file_to_record.get(_normkey(fname)))
            size = os.path.getsize(full)
            payload = {
                'filename': fname,
                'type': ftype_label,
                'size': size,
                'size_display': f'{size/1024:.1f} KB',
                'create_time': datetime.fromtimestamp(os.path.getmtime(full)).strftime('%Y-%m-%d %H:%M'),
                'source_record': rec,  # 模板可反查对应巡检/故障/工单
            }
            if rec and rec.customer_id:
                cust = customers_index.get(rec.customer_id) or rec.customer_rel
                _push_record(cust.id, cust.name, 'file', None, None, payload)
            else:
                _push_record(None, '未关联客户', 'file', None, None, payload,
                             unassigned=True)

    # --- 排序：真实客户按 name，未关联固定末位 ---
    real = sorted([v for k, v in data.items() if k is not None], key=lambda x: x['name'])
    unassigned = data.get(None)
    data_order = real + ([unassigned] if unassigned else [])

    # --- tab 统计：每个 tab 下的覆盖客户数 / 总记录数 ---
    def _tcount(p, t):
        return p['counts'].get(t, 0)

    def _has_any(p):
        return any(p['counts'].values())

    tab_stats = {
        'all': {
            'customers': sum(1 for p in data_order if _has_any(p)),
            'total': sum(sum(p['counts'].values()) for p in data_order),
        },
        'inspection': {
            'customers': sum(1 for p in data_order if _tcount(p, 'inspection')),
            'total': sum(_tcount(p, 'inspection') for p in data_order),
        },
        'fault': {
            'customers': sum(1 for p in data_order if _tcount(p, 'fault')),
            'total': sum(_tcount(p, 'fault') for p in data_order),
        },
        'ticket': {
            'customers': sum(1 for p in data_order if _tcount(p, 'ticket')),
            'total': sum(_tcount(p, 'ticket') for p in data_order),
        },
        'file': {
            'customers': sum(1 for p in data_order if _tcount(p, 'file')),
            'total': sum(_tcount(p, 'file') for p in data_order),
        },
    }

    return render_template(
        'reports/list.html',
        data_order=data_order,
        customers=customers_index,
        tab=tab,
        tab_stats=tab_stats,
        scope=scope, date_from=date_from, date_to=date_to, customer_id=customer_id,
        default_window=default_window,
    )


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
        return redirect(url_for('ops.report_list'))
    os.remove(full)
    current_app.logger.info(
        '报告删除审计: 用户[%s] 删除报告[%s], IP=%s',
        current_user.username, os.path.basename(full), request.remote_addr)
    flash('已删除', 'success')
    return redirect(url_for('ops.report_list'))


@ops_bp.route('/reports/<path:filename>')
@login_required
@require_permission('report:view')
def report_download(filename):
    full = _safe_report_path(filename)
    if full is None:
        abort(404)
    return send_from_directory(os.path.dirname(full), os.path.basename(full), as_attachment=True)
