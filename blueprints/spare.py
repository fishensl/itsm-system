# -*- coding: utf-8 -*-
"""备件导出（SSR CRUD 已由 Vue SPA /api/* 接管）"""
from datetime import date
from flask import Blueprint
from flask_login import login_required
from models import SparePart
from utils.permission import require_permission

spare_bp = Blueprint('spare', __name__)


@spare_bp.route('/spare-parts/export')
@login_required
@require_permission('spare:view')
def spare_export():
    """导出备件档案到 Excel（统一走 utils.excel_export，绿色表头）"""
    from utils.excel_export import export_xlsx, send_temp_export
    headers = ['编码', '名称', '品牌', '型号', '厂家', '分类', '规格', '参数',
               '单位', '参考价', '保修期(月)', '最低库存', '序列号', '备注']
    rows = [[p.code, p.name, p.brand, p.model, p.manufacturer,
             p.category, p.specification, p.parameters,
             p.unit, p.reference_price, p.warranty_months,
             p.min_stock, p.serial_number, p.remark]
            for p in SparePart.query.order_by(SparePart.id).all()]
    path, download_name = export_xlsx(
        headers, rows, f'备件档案_{date.today().isoformat()}.xlsx',
        sheet_name='备件档案', header_color=('52C41A', '389E0D'))
    return send_temp_export(path, download_name)
