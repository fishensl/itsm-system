# -*- coding: utf-8 -*-
"""故障导出 + 故障类型 API（SSR CRUD 已由 Vue SPA /api/* 接管）"""
import os
from flask import request, send_from_directory, jsonify
from flask_login import login_required
from sqlalchemy.orm import joinedload
from models import Fault, FaultType, db
from utils.permission import require_permission
from blueprints.ops import ops_bp


@ops_bp.route('/faults/export')
@login_required
@require_permission('fault:view')
def fault_export():
    # 统一走 utils.excel_export；joinedload 消除逐行 customer N+1
    from datetime import date
    from utils.excel_export import export_xlsx
    rows = [[f.title, f.customer_rel.name if f.customer_rel else '-', f.handler or '',
             f.fault_time.strftime('%Y-%m-%d %H:%M') if f.fault_time else '',
             f.result or '']
            for f in Fault.query.options(joinedload(Fault.customer_rel))
            .order_by(Fault.id.desc()).all()]
    path, download_name = export_xlsx(
        ['标题', '客户', '处理人', '故障时间', '结果'], rows,
        f'故障导出_{date.today().isoformat()}.xlsx', sheet_name='故障记录')
    return send_from_directory(os.path.dirname(path), os.path.basename(path),
                               as_attachment=True, download_name=download_name)


# ============================ 故障类型 (API) ============================
@ops_bp.route('/api/fault-types/add', methods=['POST'])
@login_required
@require_permission('fault:edit')
def api_fault_type_add():
    """JSON API：工单表单内快速新增故障类别（重名校验，sort_order 自动排尾）"""
    data = request.get_json(silent=True) or request.form
    name = (data.get('name') or '').strip()
    if not name:
        return jsonify({'success': False, 'error': '类别名称不能为空'}), 400
    if FaultType.query.filter_by(name=name).first():
        return jsonify({'success': False, 'error': f'类别「{name}」已存在'}), 409
    max_order = db.session.query(db.func.max(FaultType.sort_order)).scalar() or 0
    t = FaultType(name=name, sort_order=max_order + 1)
    db.session.add(t)
    db.session.commit()
    return jsonify({'success': True, 'id': t.id, 'name': t.name})
