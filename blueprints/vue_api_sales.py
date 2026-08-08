# -*- coding: utf-8 -*-
"""Vue SPA 业务 API（商务域：备件 / 销售管线）

复用 blueprints.vue_api 的 vue_api_bp 蓝图对象与 ok/fail 契约，
避免单一文件膨胀与并行开发冲突。由 blueprints/__init__ 注册。
"""
from flask import request, current_app
from flask_login import login_required, current_user
from sqlalchemy import func
from sqlalchemy.orm import joinedload as _jl

from models import (db, SparePart, SpareStock, PurchaseOrder, SalesOrder, Customer,
                    Opportunity, Quotation, Contract, Project, InspectionTaskTemplate)
from utils.permission import require_permission
from utils import constants as _const

from blueprints.vue_api import vue_api_bp, ok, fail, _FormAdapter  # noqa: F401  (统一契约)

OPP_STAGES = list(_const.OPP_STAGES)
QUOTATION_STATUSES = ['草稿', '已发送', '已接受', '已拒绝']
CONTRACT_STATUSES = ['草签', '已签', '执行中', '已完成', '已终止']
PROJECT_STATUSES = ['未启动', '进行中', '已完成', '已暂停']
CONTRACT_FREQUENCIES = ['每月', '每季度', '每半年', '每年']


def _me():
    return current_user.realname or current_user.username


def _fmt_date(d):
    return d.strftime('%Y-%m-%d') if d else ''


def _fmt_dt(d):
    return d.strftime('%Y-%m-%d %H:%M') if d else ''


# ==================== 备件档案 ====================
def _spare_total_stock(spare_id):
    return db.session.query(func.coalesce(func.sum(SpareStock.quantity), 0)) \
        .filter(SpareStock.spare_part_id == spare_id).scalar() or 0


def _spare_part_payload(p, total_stock=None):
    total = int(total_stock if total_stock is not None else 0)
    min_stock = p.min_stock or 0
    return {
        'id': p.id,
        'code': p.code or '',
        'name': p.name,
        'category': p.category or '',
        'brand': p.brand or '',
        'model': p.model or '',
        'specification': p.specification or '',
        'unit': p.unit or '个',
        'min_stock': min_stock,
        'reference_price': p.reference_price or 0,
        'warranty_months': p.warranty_months or 0,
        'manufacturer': p.manufacturer or '',
        'serial_number': p.serial_number or '',
        'remark': p.remark or '',
        'total_stock': total,
        'stock_alert': bool(min_stock > 0 and total < min_stock),
        'stock_alert_label': '库存预警' if (min_stock > 0 and total < min_stock) else '正常',
        'created_at': _fmt_dt(p.created_at),
    }


@vue_api_bp.route('/api/spare-parts', methods=['GET'])
@login_required
@require_permission('spare:view')
def api_spare_part_list():
    """备件分页列表（LEFT JOIN 库存聚合：总库存 + 预警标记）"""
    page = request.args.get('page', 1, type=int)
    page_size = min(request.args.get('page_size', 20, type=int), 100)
    search = (request.args.get('search') or '').strip()
    category = (request.args.get('category') or '').strip()

    stock_sum = db.session.query(
        SpareStock.spare_part_id,
        func.sum(SpareStock.quantity).label('total'),
    ).group_by(SpareStock.spare_part_id).subquery()

    q = db.session.query(SparePart, func.coalesce(stock_sum.c.total, 0)) \
        .outerjoin(stock_sum, stock_sum.c.spare_part_id == SparePart.id)
    if search:
        q = q.filter(SparePart.name.contains(search) | SparePart.code.contains(search) |
                     SparePart.brand.contains(search) | SparePart.model.contains(search))
    if category:
        q = q.filter(SparePart.category == category)
    total = q.count()
    rows = q.order_by(SparePart.id.desc()) \
        .offset((page - 1) * page_size).limit(page_size).all()
    return ok({'items': [_spare_part_payload(p, t) for p, t in rows],
               'total': total, 'page': page, 'page_size': page_size})


@vue_api_bp.route('/api/spare-parts/export', methods=['POST'])
@login_required
@require_permission('spare:view')
def api_spare_part_export():
    """备件导出（base64 xlsx；columns + 创建时间范围）"""
    import base64
    import os
    from datetime import date as _date
    from utils.excel_export import export_xlsx
    from blueprints.vue_export import SPARE_EXPORT_COLUMNS, resolve_columns, generic_rows
    data = request.get_json(silent=True) or {}
    try:
        codes = resolve_columns(SPARE_EXPORT_COLUMNS, data.get('columns'))
    except ValueError as e:
        return fail(str(e), 400)
    stock_sum = db.session.query(
        SpareStock.spare_part_id,
        func.sum(SpareStock.quantity).label('total'),
    ).group_by(SpareStock.spare_part_id).subquery()
    q = db.session.query(SparePart, func.coalesce(stock_sum.c.total, 0)) \
        .outerjoin(stock_sum, stock_sum.c.spare_part_id == SparePart.id)
    date_from = (data.get('date_from') or '').strip()
    date_to = (data.get('date_to') or '').strip()
    if date_from:
        q = q.filter(SparePart.created_at >= date_from)
    if date_to:
        q = q.filter(SparePart.created_at <= date_to + ' 23:59:59')
    rows = q.order_by(SparePart.id.desc()).all()
    stock_map = {p.id: int(t or 0) for p, t in rows}
    headers = [dict(SPARE_EXPORT_COLUMNS)[c] for c in codes]

    def cell(p, code):
        return {
            'code': p.code or '', 'name': p.name, 'category': p.category or '',
            'specification': p.specification or '', 'unit': p.unit or '个',
            'brand': p.brand or '', 'model': p.model or '',
            'serial_number': p.serial_number or '', 'manufacturer': p.manufacturer or '',
            'quantity': stock_map.get(p.id, 0), 'min_stock': p.min_stock or 0,
            'remark': p.remark or '',
            'created_at': p.created_at.strftime('%Y-%m-%d') if p.created_at else '',
        }.get(code, '')

    out_rows = generic_rows([p for p, _ in rows], codes, cell)
    tmp_path, download_name = export_xlsx(headers, out_rows,
                                          f'备件导出_{_date.today().isoformat()}.xlsx',
                                          sheet_name='备件档案')
    with open(tmp_path, 'rb') as fh:
        b64 = base64.b64encode(fh.read()).decode('ascii')
    try:
        os.remove(tmp_path)
    except OSError:
        pass
    return ok({'filename': download_name, 'content': b64})


@vue_api_bp.route('/api/spare-parts/<int:spare_id>', methods=['GET'])
@login_required
@require_permission('spare:view')
def api_spare_part_get(spare_id):
    p = SparePart.query.get_or_404(spare_id)
    customer_map = {c.id: c.name for c in Customer.query.all()}
    payload = _spare_part_payload(p, _spare_total_stock(p.id))
    payload['stocks'] = [{
        'id': s.id, 'spare_part_id': s.spare_part_id, 'location': s.location or '',
        'quantity': s.quantity or 0, 'unit_price': s.unit_price or 0,
        'updated_at': _fmt_dt(s.updated_at),
    } for s in p.stocks]
    payload['purchases'] = [{
        'id': po.id, 'number': po.number or '', 'supplier_name': po.supplier_name or '',
        'quantity': po.quantity or 0, 'unit_price': po.unit_price or 0,
        'total': po.total or 0, 'purchase_date': _fmt_date(po.purchase_date),
        'operator': po.operator or '', 'remark': po.remark or '',
        'created_at': _fmt_dt(po.created_at),
    } for po in p.purchases]
    payload['sales'] = [{
        'id': so.id, 'number': so.number or '',
        'customer_id': so.customer_id,
        'customer_name': customer_map.get(so.customer_id, ''),
        'quantity': so.quantity or 0, 'unit_price': so.unit_price or 0,
        'total': so.total or 0, 'sales_date': _fmt_date(so.sales_date),
        'operator': so.operator or '', 'invoice_number': so.invoice_number or '',
        'remark': so.remark or '', 'created_at': _fmt_dt(so.created_at),
    } for so in p.sales]
    return ok(payload)


@vue_api_bp.route('/api/spare-parts', methods=['POST'])
@login_required
@require_permission('spare:add')
def api_spare_part_create():
    from services.spare_service import create_spare_part
    data = request.get_json(silent=True) or {}
    try:
        p = create_spare_part(data)
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        return fail(str(e) or '备件创建失败', 400)
    return ok({'id': p.id})


@vue_api_bp.route('/api/spare-parts/<int:spare_id>', methods=['PUT'])
@login_required
@require_permission('spare:edit')
def api_spare_part_update(spare_id):
    from services.spare_service import update_spare_part
    data = request.get_json(silent=True) or {}
    try:
        p = update_spare_part(spare_id, data)
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        return fail(str(e) or '备件更新失败', 400)
    return ok({'id': p.id})


@vue_api_bp.route('/api/spare-parts/<int:spare_id>', methods=['DELETE'])
@login_required
@require_permission('spare:delete')
def api_spare_part_delete(spare_id):
    from services.spare_service import delete_spare_part
    try:
        delete_spare_part(spare_id)
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        return fail(str(e) or '备件删除失败', 400)
    return ok(None)


# ==================== 备件库存 ====================
def _spare_stock_payload(s):
    return {
        'id': s.id,
        'spare_part_id': s.spare_part_id,
        'spare_part_name': s.spare_part_rel.name if s.spare_part_rel else '',
        'location': s.location or '',
        'quantity': s.quantity or 0,
        'unit_price': s.unit_price or 0,
        'updated_at': _fmt_dt(s.updated_at),
    }


@vue_api_bp.route('/api/spare-stocks', methods=['GET'])
@login_required
@require_permission('spare:view')
def api_spare_stock_list():
    page = request.args.get('page', 1, type=int)
    page_size = min(request.args.get('page_size', 20, type=int), 100)
    search = (request.args.get('search') or '').strip()
    spare_part_id = request.args.get('spare_part_id', type=int)

    q = SpareStock.query.options(_jl(SpareStock.spare_part_rel))
    if spare_part_id:
        q = q.filter(SpareStock.spare_part_id == spare_part_id)
    elif search:
        q = q.join(SparePart, SparePart.id == SpareStock.spare_part_id) \
            .filter(SparePart.name.contains(search) | SparePart.code.contains(search))
    total = q.count()
    rows = q.order_by(SpareStock.id.desc()) \
        .offset((page - 1) * page_size).limit(page_size).all()
    return ok({'items': [_spare_stock_payload(s) for s in rows],
               'total': total, 'page': page, 'page_size': page_size})


@vue_api_bp.route('/api/spare-stocks', methods=['POST'])
@login_required
@require_permission('spare:add')
def api_spare_stock_create():
    from services.spare_service import _record_movement
    data = request.get_json(silent=True) or {}
    if not data.get('spare_part_id'):
        return fail('请选择备件', 400)
    qty = int(data.get('quantity') or 0)
    if qty < 0:
        return fail('库存数量不能为负数', 400)
    s = SpareStock(
        spare_part_id=int(data['spare_part_id']),
        location=data.get('location') or '默认库位',
        quantity=qty,
        unit_price=float(data.get('unit_price') or 0),
    )
    db.session.add(s)
    db.session.flush()
    _record_movement(s.spare_part_id, 'adjust', qty, current_user.realname or current_user.username,
                     balance_after=qty, location=s.location, source_id=s.id,
                     remark='新增库存行（盘点）')
    db.session.commit()
    return ok({'id': s.id})


@vue_api_bp.route('/api/spare-stocks/<int:stock_id>', methods=['PUT'])
@login_required
@require_permission('spare:edit')
def api_spare_stock_update(stock_id):
    from services.spare_service import _record_movement
    data = request.get_json(silent=True) or {}
    qty = int(data.get('quantity') or 0)
    if qty < 0:
        return fail('库存数量不能为负数', 400)
    s = SpareStock.query.get_or_404(stock_id)
    old_qty = s.quantity or 0
    if data.get('spare_part_id'):
        s.spare_part_id = int(data['spare_part_id'])
    s.location = data.get('location', s.location) or ''
    s.quantity = qty
    if 'unit_price' in data:
        s.unit_price = float(data.get('unit_price') or 0)
    if qty != old_qty:
        _record_movement(s.spare_part_id, 'adjust', qty - old_qty,
                         current_user.realname or current_user.username,
                         location=s.location, source_id=s.id, remark='库存盘点调整')
    db.session.commit()
    return ok({'id': s.id})


@vue_api_bp.route('/api/spare-stocks/<int:stock_id>', methods=['DELETE'])
@login_required
@require_permission('spare:delete')
def api_spare_stock_delete(stock_id):
    from services.spare_service import _record_movement
    s = SpareStock.query.get_or_404(stock_id)
    _record_movement(s.spare_part_id, 'adjust', -(s.quantity or 0),
                     current_user.realname or current_user.username,
                     location=s.location or '', source_id=s.id, remark='删除库存行')
    db.session.delete(s)
    db.session.commit()
    return ok(None)


# ==================== 采购入库 / 销售出库 ====================
def _purchase_payload(po):
    return {
        'id': po.id,
        'number': po.number or '',
        'spare_part_id': po.spare_part_id,
        'spare_part_name': po.spare_part_rel.name if po.spare_part_rel else '',
        'supplier_name': po.supplier_name or '',
        'quantity': po.quantity or 0,
        'unit_price': po.unit_price or 0,
        'total': po.total or 0,
        'purchase_date': _fmt_date(po.purchase_date),
        'operator': po.operator or '',
        'remark': po.remark or '',
        'created_at': _fmt_dt(po.created_at),
    }


def _sales_payload(so, customer_map=None):
    return {
        'id': so.id,
        'number': so.number or '',
        'spare_part_id': so.spare_part_id,
        'spare_part_name': so.spare_part_rel.name if so.spare_part_rel else '',
        'customer_id': so.customer_id,
        'customer_name': (customer_map or {}).get(so.customer_id, ''),
        'quantity': so.quantity or 0,
        'unit_price': so.unit_price or 0,
        'total': so.total or 0,
        'sales_date': _fmt_date(so.sales_date),
        'operator': so.operator or '',
        'invoice_number': so.invoice_number or '',
        'remark': so.remark or '',
        'created_at': _fmt_dt(so.created_at),
    }


@vue_api_bp.route('/api/purchase-orders', methods=['GET'])
@login_required
@require_permission('spare:view')
def api_purchase_order_list():
    page = request.args.get('page', 1, type=int)
    page_size = min(request.args.get('page_size', 20, type=int), 100)
    search = (request.args.get('search') or '').strip()
    spare_part_id = request.args.get('spare_part_id', type=int)

    q = PurchaseOrder.query.options(_jl(PurchaseOrder.spare_part_rel))
    if spare_part_id:
        q = q.filter(PurchaseOrder.spare_part_id == spare_part_id)
    elif search:
        q = q.join(SparePart, SparePart.id == PurchaseOrder.spare_part_id) \
            .filter(SparePart.name.contains(search) |
                    PurchaseOrder.supplier_name.contains(search))
    total = q.count()
    rows = q.order_by(PurchaseOrder.id.desc()) \
        .offset((page - 1) * page_size).limit(page_size).all()
    return ok({'items': [_purchase_payload(po) for po in rows],
               'total': total, 'page': page, 'page_size': page_size})


@vue_api_bp.route('/api/purchase-orders', methods=['POST'])
@login_required
@require_permission('spare:add')
def api_purchase_order_create():
    from services.spare_service import create_purchase_order
    data = request.get_json(silent=True) or {}
    try:
        po = create_purchase_order(data, _me())
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        return fail(str(e) or '采购入库失败', 400)
    return ok({'id': po.id})


@vue_api_bp.route('/api/purchase-orders/<int:po_id>', methods=['DELETE'])
@login_required
@require_permission('spare:delete')
def api_purchase_order_delete(po_id):
    from services.spare_service import delete_purchase_order
    try:
        delete_purchase_order(po_id)
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        return fail(str(e) or '采购单删除失败', 400)
    return ok(None)


@vue_api_bp.route('/api/sales-orders', methods=['GET'])
@login_required
@require_permission('spare:view')
def api_sales_order_list():
    page = request.args.get('page', 1, type=int)
    page_size = min(request.args.get('page_size', 20, type=int), 100)
    search = (request.args.get('search') or '').strip()
    spare_part_id = request.args.get('spare_part_id', type=int)
    customer_id = request.args.get('customer_id', type=int)

    q = SalesOrder.query.options(_jl(SalesOrder.spare_part_rel), _jl(SalesOrder.customer_rel))
    if spare_part_id:
        q = q.filter(SalesOrder.spare_part_id == spare_part_id)
    if customer_id:
        q = q.filter(SalesOrder.customer_id == customer_id)
    if search:
        q = q.join(SparePart, SparePart.id == SalesOrder.spare_part_id) \
            .filter(SparePart.name.contains(search))
    total = q.count()
    rows = q.order_by(SalesOrder.id.desc()) \
        .offset((page - 1) * page_size).limit(page_size).all()
    customer_map = {c.id: c.name for c in Customer.query.all()}
    return ok({'items': [_sales_payload(so, customer_map) for so in rows],
               'total': total, 'page': page, 'page_size': page_size})


@vue_api_bp.route('/api/sales-orders', methods=['POST'])
@login_required
@require_permission('spare:add')
def api_sales_order_create():
    from services.spare_service import create_sales_order, _check_low_stock
    data = request.get_json(silent=True) or {}
    try:
        so = create_sales_order(data, _me())
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        return fail(str(e) or '销售出库失败', 400)
    # 事件源：出库后低库存预警
    _check_low_stock(so.spare_part_id, _me())
    return ok({'id': so.id})


@vue_api_bp.route('/api/sales-orders/<int:so_id>', methods=['DELETE'])
@login_required
@require_permission('spare:delete')
def api_sales_order_delete(so_id):
    from services.spare_service import delete_sales_order
    try:
        delete_sales_order(so_id)
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        return fail(str(e) or '销售单删除失败', 400)
    return ok(None)


@vue_api_bp.route('/api/dicts/spare', methods=['GET'])
@login_required
@require_permission('spare:view')
def api_spare_dicts():
    parts = [{'id': p.id, 'name': p.name}
             for p in SparePart.query.order_by(SparePart.name).all()]
    customers = [{'id': c.id, 'name': c.name}
                 for c in Customer.query.order_by(Customer.name).all()]
    categories = [r[0] for r in db.session.query(SparePart.category).distinct()
                  .filter(SparePart.category != '').order_by(SparePart.category).all()]
    return ok({'spare_parts': parts, 'customers': customers, 'categories': categories})


# ==================== 商机 ====================
def _opportunity_payload(o, customer_map=None):
    return {
        'id': o.id,
        'customer_id': o.customer_id,
        'customer_name': (customer_map or {}).get(o.customer_id, ''),
        'title': o.title,
        'stage': o.stage or '初步接触',
        'expected_amount': o.expected_amount or 0,
        'expected_close_date': _fmt_date(o.expected_close_date),
        'owner': o.owner or '',
        'remark': o.remark or '',
        'created_at': _fmt_dt(o.created_at),
    }


@vue_api_bp.route('/api/opportunities', methods=['GET'])
@login_required
@require_permission('sales:view')
def api_opportunity_list():
    page = request.args.get('page', 1, type=int)
    page_size = min(request.args.get('page_size', 20, type=int), 100)
    search = (request.args.get('search') or '').strip()
    stage = (request.args.get('stage') or '').strip()

    q = Opportunity.query
    if search:
        q = q.filter(Opportunity.title.contains(search))
    if stage:
        q = q.filter(Opportunity.stage == stage)
    total = q.count()
    rows = q.order_by(Opportunity.id.desc()) \
        .offset((page - 1) * page_size).limit(page_size).all()
    customer_map = {c.id: c.name for c in Customer.query.all()}
    return ok({'items': [_opportunity_payload(o, customer_map) for o in rows],
               'total': total, 'page': page, 'page_size': page_size})


@vue_api_bp.route('/api/opportunities/<int:opp_id>', methods=['GET'])
@login_required
@require_permission('sales:view')
def api_opportunity_get(opp_id):
    o = Opportunity.query.get_or_404(opp_id)
    return ok(_opportunity_payload(o, {o.customer_id: o.customer_rel.name if o.customer_rel else ''}))


@vue_api_bp.route('/api/opportunities', methods=['POST'])
@login_required
@require_permission('sales:add')
def api_opportunity_create():
    from services.sales_service import create_opportunity
    data = request.get_json(silent=True) or {}
    try:
        o = create_opportunity(data, _me())
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        return fail(str(e) or '商机创建失败', 400)
    return ok({'id': o.id})


@vue_api_bp.route('/api/opportunities/<int:opp_id>', methods=['PUT'])
@login_required
@require_permission('sales:edit')
def api_opportunity_update(opp_id):
    from services.sales_service import update_opportunity
    data = request.get_json(silent=True) or {}
    try:
        o = update_opportunity(opp_id, data)
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        return fail(str(e) or '商机更新失败', 400)
    return ok({'id': o.id})


@vue_api_bp.route('/api/opportunities/<int:opp_id>', methods=['DELETE'])
@login_required
@require_permission('sales:delete')
def api_opportunity_delete(opp_id):
    from services.sales_service import delete_opportunity
    try:
        delete_opportunity(opp_id)
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        return fail(str(e) or '商机删除失败', 400)
    return ok(None)


# ==================== 报价单 ====================
def _quotation_payload(q, customer_map=None, opp_map=None):
    from utils.json_fields import parse_json
    return {
        'id': q.id,
        'number': q.number or '',
        'opportunity_id': q.opportunity_id,
        'opportunity_title': (opp_map or {}).get(q.opportunity_id, ''),
        'customer_id': q.customer_id,
        'customer_name': (customer_map or {}).get(q.customer_id, ''),
        'total_amount': q.total_amount or 0,
        'valid_until': _fmt_date(q.valid_until),
        'status': q.status or '草稿',
        'items': parse_json(q.items_json, [], 'quotation.items_json'),
        'created_at': _fmt_dt(q.created_at),
    }


@vue_api_bp.route('/api/quotations', methods=['GET'])
@login_required
@require_permission('sales:view')
def api_quotation_list():
    page = request.args.get('page', 1, type=int)
    page_size = min(request.args.get('page_size', 20, type=int), 100)
    search = (request.args.get('search') or '').strip()
    status = (request.args.get('status') or '').strip()

    q = Quotation.query
    if search:
        q = q.filter(Quotation.number.contains(search))
    if status:
        q = q.filter(Quotation.status == status)
    total = q.count()
    rows = q.order_by(Quotation.id.desc()) \
        .offset((page - 1) * page_size).limit(page_size).all()
    customer_map = {c.id: c.name for c in Customer.query.all()}
    opp_map = {o.id: o.title for o in Opportunity.query.all()}
    return ok({'items': [_quotation_payload(qt, customer_map, opp_map) for qt in rows],
               'total': total, 'page': page, 'page_size': page_size})


@vue_api_bp.route('/api/quotations', methods=['POST'])
@login_required
@require_permission('sales:add')
def api_quotation_create():
    from services.sales_service import create_quotation
    data = request.get_json(silent=True) or {}
    try:
        q = create_quotation(data, _me())
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        return fail(str(e) or '报价单创建失败', 400)
    return ok({'id': q.id})


@vue_api_bp.route('/api/quotations/<int:quot_id>', methods=['PUT'])
@login_required
@require_permission('sales:edit')
def api_quotation_update(quot_id):
    from services.sales_service import update_quotation
    data = request.get_json(silent=True) or {}
    try:
        q = update_quotation(quot_id, data)
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        return fail(str(e) or '报价单更新失败', 400)
    return ok({'id': q.id})


@vue_api_bp.route('/api/quotations/<int:quot_id>', methods=['DELETE'])
@login_required
@require_permission('sales:delete')
def api_quotation_delete(quot_id):
    from services.sales_service import delete_quotation
    try:
        delete_quotation(quot_id)
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        return fail(str(e) or '报价单删除失败', 400)
    return ok(None)


# ==================== 合同 ====================
def _gen_contract_tasks(c):
    """合同保存后自动生成巡检任务（与 SSR after 钩子逻辑一致；失败仅记日志）"""
    if not (c and c.inspection_frequency and c.auto_generate_tasks
            and (c.task_template_id or c.inspection_template_id)):
        return 0
    try:
        from utils.auto_task_generator import generate_contract_tasks
        return len(generate_contract_tasks(contract_id=c.id))
    except Exception:
        current_app.logger.exception('合同 %s 自动任务生成失败(Vue)', c.id)
        return 0


def _contract_payload(c, customer_map=None, template_map=None):
    return {
        'id': c.id,
        'number': c.number or '',
        'title': c.title,
        'customer_id': c.customer_id,
        'customer_name': (customer_map or {}).get(c.customer_id, ''),
        'opportunity_id': c.opportunity_id,
        'amount': c.amount or 0,
        'status': c.status or '执行中',
        'start_date': _fmt_date(c.start_date),
        'end_date': _fmt_date(c.end_date),
        'inspection_frequency': c.inspection_frequency or '',
        'task_template_id': c.task_template_id,
        'task_template_name': (template_map or {}).get(c.task_template_id, ''),
        'auto_generate_tasks': bool(c.auto_generate_tasks),
        'created_at': _fmt_dt(c.created_at),
    }


@vue_api_bp.route('/api/contracts', methods=['GET'])
@login_required
@require_permission('sales:view')
def api_contract_list():
    page = request.args.get('page', 1, type=int)
    page_size = min(request.args.get('page_size', 20, type=int), 100)
    search = (request.args.get('search') or '').strip()
    status = (request.args.get('status') or '').strip()

    q = Contract.query
    if search:
        q = q.filter(Contract.title.contains(search) | Contract.number.contains(search))
    if status:
        q = q.filter(Contract.status == status)
    total = q.count()
    rows = q.order_by(Contract.id.desc()) \
        .offset((page - 1) * page_size).limit(page_size).all()
    customer_map = {c.id: c.name for c in Customer.query.all()}
    template_map = {t.id: t.name for t in InspectionTaskTemplate.query.all()}
    return ok({'items': [_contract_payload(c, customer_map, template_map) for c in rows],
               'total': total, 'page': page, 'page_size': page_size})


@vue_api_bp.route('/api/contracts', methods=['POST'])
@login_required
@require_permission('sales:add')
def api_contract_create():
    from services.sales_service import create_contract
    data = request.get_json(silent=True) or {}
    try:
        c = create_contract(data, _me())
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        return fail(str(e) or '合同创建失败', 400)
    generated = _gen_contract_tasks(c)
    return ok({'id': c.id, 'generated': generated})


@vue_api_bp.route('/api/contracts/<int:contract_id>', methods=['PUT'])
@login_required
@require_permission('sales:edit')
def api_contract_update(contract_id):
    from services.sales_service import update_contract
    data = request.get_json(silent=True) or {}
    # 整表单 PUT 语义：显式携带 checkbox 标记，允许清空自动生成配置
    data['inspection_config_present'] = True
    try:
        c = update_contract(contract_id, data)
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        return fail(str(e) or '合同更新失败', 400)
    generated = _gen_contract_tasks(c)
    return ok({'id': c.id, 'generated': generated})


@vue_api_bp.route('/api/contracts/<int:contract_id>', methods=['DELETE'])
@login_required
@require_permission('sales:delete')
def api_contract_delete(contract_id):
    from services.sales_service import delete_contract
    try:
        delete_contract(contract_id)
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        return fail(str(e) or '合同删除失败', 400)
    return ok(None)


# ==================== 项目 ====================
def _project_payload(p, customer_map=None, contract_map=None):
    return {
        'id': p.id,
        'name': p.name,
        'contract_id': p.contract_id,
        'contract_title': (contract_map or {}).get(p.contract_id, ''),
        'customer_id': p.customer_id,
        'customer_name': (customer_map or {}).get(p.customer_id, ''),
        'manager': p.manager or '',
        'status': p.status or '未启动',
        'start_date': _fmt_date(p.start_date),
        'end_date': _fmt_date(p.end_date),
        'progress': p.progress or 0,
        'budget': p.budget or 0,
        'created_at': _fmt_dt(p.created_at),
    }


@vue_api_bp.route('/api/projects', methods=['GET'])
@login_required
@require_permission('sales:view')
def api_project_list():
    page = request.args.get('page', 1, type=int)
    page_size = min(request.args.get('page_size', 20, type=int), 100)
    search = (request.args.get('search') or '').strip()
    status = (request.args.get('status') or '').strip()

    q = Project.query
    if search:
        q = q.filter(Project.name.contains(search))
    if status:
        q = q.filter(Project.status == status)
    total = q.count()
    rows = q.order_by(Project.id.desc()) \
        .offset((page - 1) * page_size).limit(page_size).all()
    customer_map = {c.id: c.name for c in Customer.query.all()}
    contract_map = {ct.id: ct.title for ct in Contract.query.all()}
    return ok({'items': [_project_payload(p, customer_map, contract_map) for p in rows],
               'total': total, 'page': page, 'page_size': page_size})


@vue_api_bp.route('/api/projects', methods=['POST'])
@login_required
@require_permission('sales:add')
def api_project_create():
    from services.sales_service import create_project
    data = request.get_json(silent=True) or {}
    try:
        p = create_project(data, _me())
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        return fail(str(e) or '项目创建失败', 400)
    return ok({'id': p.id})


@vue_api_bp.route('/api/projects/<int:project_id>', methods=['PUT'])
@login_required
@require_permission('sales:edit')
def api_project_update(project_id):
    from services.sales_service import update_project
    data = request.get_json(silent=True) or {}
    try:
        p = update_project(project_id, data)
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        return fail(str(e) or '项目更新失败', 400)
    return ok({'id': p.id})


@vue_api_bp.route('/api/projects/<int:project_id>', methods=['DELETE'])
@login_required
@require_permission('sales:delete')
def api_project_delete(project_id):
    from services.sales_service import delete_project
    try:
        delete_project(project_id)
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        return fail(str(e) or '项目删除失败', 400)
    return ok(None)


@vue_api_bp.route('/api/dicts/sales', methods=['GET'])
@login_required
@require_permission('sales:view')
def api_sales_dicts():
    customers = [{'id': c.id, 'name': c.name}
                 for c in Customer.query.order_by(Customer.name).all()]
    opportunities = [{'id': o.id, 'title': o.title}
                     for o in Opportunity.query.order_by(Opportunity.id.desc()).limit(200).all()]
    contracts = [{'id': c.id, 'title': c.title}
                 for c in Contract.query.order_by(Contract.id.desc()).limit(200).all()]
    templates = [{'id': t.id, 'name': t.name}
                 for t in InspectionTaskTemplate.query.filter_by(is_active=True)
                 .order_by(InspectionTaskTemplate.name).all()]
    return ok({
        'opp_stages': OPP_STAGES,
        'quotation_statuses': QUOTATION_STATUSES,
        'contract_statuses': CONTRACT_STATUSES,
        'project_statuses': PROJECT_STATUSES,
        'frequencies': CONTRACT_FREQUENCIES,
        'customers': customers,
        'opportunities': opportunities,
        'contracts': contracts,
        'templates': templates,
    })

# ==================== 合同巡检配置 ====================
@vue_api_bp.route('/api/contract-tasks', methods=['GET'])
@login_required
@require_permission('contract_auto:manage')
def api_contract_tasks_list():
    from models import Contract, InspectionTaskTemplate, Customer
    contracts = Contract.query.filter(
        Contract.inspection_frequency != '',
        Contract.inspection_frequency.isnot(None),
    ).order_by(Contract.id.desc()).all()
    all_contracts = Contract.query.order_by(Contract.id.desc()).all()
    templates = InspectionTaskTemplate.query.filter_by(is_active=True) \
        .order_by(InspectionTaskTemplate.name).all()
    customer_map = {c.id: c.name for c in Customer.query.all()}
    return ok({
        'contracts': [
            {
                'id': c.id,
                'title': c.title,
                'customer_name': customer_map.get(c.customer_id, '-'),
                'inspection_frequency': c.inspection_frequency or '',
                'auto_generate_tasks': bool(c.auto_generate_tasks),
                'task_template_id': c.task_template_id,
                'end_date': c.end_date.strftime('%Y-%m-%d') if c.end_date else '',
            }
            for c in contracts
        ],
        'all_contracts': [
            {
                'id': c.id,
                'title': c.title,
                'customer_name': customer_map.get(c.customer_id, '-'),
                'inspection_frequency': c.inspection_frequency or '',
            }
            for c in all_contracts
        ],
        'templates': [{'id': t.id, 'name': t.name} for t in templates],
    })


@vue_api_bp.route('/api/contract-tasks/generate', methods=['POST'])
@login_required
@require_permission('contract_auto:manage')
def api_contract_tasks_generate():
    from utils.auto_task_generator import generate_contract_tasks
    data = request.get_json(silent=True) or {}
    contract_id = data.get('contract_id')
    to_date_str = (data.get('to_date') or '').strip()
    try:
        if to_date_str:
            from datetime import datetime
            to_date = datetime.strptime(to_date_str, '%Y-%m-%d').date()
        else:
            from datetime import date
            to_date = date.today()
        generated = generate_contract_tasks(contract_id=contract_id, to_date=to_date)
        return ok({'count': len(generated), 'tasks': generated})
    except Exception as e:
        current_app.logger.exception('生成合同任务失败: contract_id=%s', contract_id)
        return fail(f'生成失败：{e}')


@vue_api_bp.route('/api/contract-tasks/preview/<int:contract_id>', methods=['GET'])
@login_required
@require_permission('contract_auto:manage')
def api_contract_tasks_preview(contract_id):
    from utils.auto_task_generator import generate_contract_tasks
    try:
        generated = generate_contract_tasks(contract_id=contract_id, dry_run=True)
        return ok({'count': len(generated), 'tasks': generated})
    except Exception as e:
        current_app.logger.exception('预览合同任务失败: contract_id=%s', contract_id)
        return fail(f'预览失败：{e}')


@vue_api_bp.route('/api/contract-tasks/generated/<int:contract_id>', methods=['GET'])
@login_required
@require_permission('contract_auto:manage')
def api_contract_tasks_generated(contract_id):
    from models import InspectionTask
    tasks = InspectionTask.query.filter_by(
        contract_id=contract_id,
        source='合同自动生成',
    ).order_by(InspectionTask.planned_start).all()
    return ok([{
        'id': t.id,
        'title': t.title,
        'status': t.status,
        'planned_start': t.planned_start.strftime('%Y-%m-%d') if t.planned_start else '',
        'planned_end': t.planned_end.strftime('%Y-%m-%d') if t.planned_end else '',
        'assigned_to': t.assigned_to_user_id,
    } for t in tasks])
