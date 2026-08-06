# -*- coding: utf-8 -*-
"""客户导出 + 地区/上级单位候选 API（SSR CRUD 与导入已由 Vue SPA /api/v2/* 接管）"""
import os
from datetime import date
from flask import (Blueprint, request, send_from_directory, jsonify)
from flask_login import login_required
from models import (Customer, Region)
from services.customer_hierarchy import candidate_parents
from utils.permission import require_permission


customer_bp = Blueprint('customer', __name__)


@customer_bp.route('/customers/export')
@login_required
@require_permission('customer:view')
def customer_export():
    """导出客户列表到 Excel（列序与导入模板保持一致，便于导出后修改再导入）"""
    from utils.excel_export import export_xlsx
    headers = ['客户名称', '联系人', '电话', '邮箱', '所属地区', '地市', '地址',
               '单位类别', '客户等级',
               '办公室', '有无驻场', '驻场联系人', '驻场联系方式', '驻场办公室',
               '有无攻防演练', '巡检频率',
               '来源', '备注']
    rows = []
    for c in Customer.query.order_by(Customer.name).all():
        # 所属地区：父级 + 自身（拼接给人看）；地市单独一列
        region_label = ''
        if c.region_rel:
            if c.region_rel.parent:
                region_label = f"{c.region_rel.parent.name} - {c.region_rel.name}"
            else:
                region_label = c.region_rel.name
        rows.append([
            c.name, c.contact_person or '', c.phone or '', c.email or '',
            region_label, c.city or '', c.address or '',
            (c.category_rel.name if c.category_rel else ''),
            c.level or '',
            c.office or '',
            '是' if c.has_onsite else '否',
            c.onsite_contact or '', c.onsite_phone or '', c.onsite_office or '',
            '是' if c.has_drill else '否',
            c.inspection_frequency or '',
            c.source or '', c.remark or '',
        ])

    tmp_path, download_name = export_xlsx(
        headers, rows,
        filename=f'客户导出_{date.today().isoformat()}.xlsx',
        sheet_name='客户信息',
    )
    return send_from_directory(
        os.path.dirname(tmp_path), os.path.basename(tmp_path),
        as_attachment=True, download_name=download_name,
    )


@customer_bp.route('/api/regions/children/<int:parent_id>')
@login_required
@require_permission('customer:view')
def api_region_children(parent_id):
    """返回指定地区的直接子地区列表（JSON），用于客户表单的市→区/县级联"""
    children = Region.query.filter_by(parent_id=parent_id)\
        .order_by(Region.sort_order, Region.id).all()
    return jsonify({'success': True, 'items': [{'id': r.id, 'name': r.name} for r in children]})


@customer_bp.route('/api/customers/parent-candidates')
@login_required
@require_permission('customer:view')
def api_parent_candidates():
    """返回指定类别下可作为「上级单位」的市级客户（JSON）。

    Query 参数：
      - category_id（必填）
      - exclude_id（可选，编辑场景排除自己 + 自己的后代）
    """
    cat_id = request.args.get('category_id', type=int)
    exclude_id = request.args.get('exclude_id', type=int)
    if not cat_id:
        return jsonify({'success': True, 'items': []})
    items = candidate_parents(cat_id, exclude_id=exclude_id)
    return jsonify({'success': True,
                    'items': [{'id': c.id, 'name': c.name} for c in items]})
