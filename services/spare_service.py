# -*- coding: utf-8 -*-
"""SparePart 备件业务服务 + 库存/采购/销售订单"""
from datetime import datetime
from models import db, SparePart, SpareStock, PurchaseOrder, SalesOrder
from .base import ServiceError, transaction


@transaction
def create_spare_part(data):
    name = (data.get('name') or '').strip()
    if not name:
        raise ServiceError('备件名称不能为空')
    if SparePart.query.filter_by(name=name).first():
        raise ServiceError(f'备件 "{name}" 已存在')
    p = SparePart(
        name=name,
        code=data.get('code', ''),
        category=data.get('category', ''),
        unit=data.get('unit', '个'),
        min_stock=int(data.get('min_stock') or 0),
        specification=data.get('specification', ''),
        remark=data.get('remark', ''),
        # V6 扩展字段
        brand=data.get('brand', ''),
        model=data.get('model', ''),
        parameters=data.get('parameters', ''),
        manufacturer=data.get('manufacturer', ''),
        image_path=data.get('image_path', ''),
        serial_number=data.get('serial_number', ''),
        reference_price=float(data.get('reference_price') or 0),
        warranty_months=int(data.get('warranty_months') or 0),
    )
    db.session.add(p)
    return p


@transaction
def update_spare_part(spare_id, data):
    p = SparePart.query.get_or_404(spare_id)
    p.name = (data.get('name') or p.name).strip()
    p.code = data.get('code', p.code)
    p.category = data.get('category', '')
    p.unit = data.get('unit', p.unit)
    p.min_stock = int(data.get('min_stock') or 0)
    p.specification = data.get('specification', '')
    p.remark = data.get('remark', '')
    # V6 扩展字段
    p.brand = data.get('brand', '')
    p.model = data.get('model', '')
    p.parameters = data.get('parameters', '')
    p.manufacturer = data.get('manufacturer', '')
    # image_path 单独处理（图片上传由路由层负责）
    if data.get('image_path') is not None:
        p.image_path = data.get('image_path', '')
    p.serial_number = data.get('serial_number', '')
    p.reference_price = float(data.get('reference_price') or 0)
    p.warranty_months = int(data.get('warranty_months') or 0)
    return p


@transaction
def delete_spare_part(spare_id):
    p = SparePart.query.get_or_404(spare_id)
    if p.stocks.count() > 0:
        raise ServiceError('该备件仍有库存记录，无法删除')
    db.session.delete(p)


@transaction
def create_purchase_order(data, current_user_name):
    """采购入库"""
    spare_id = data.get('spare_part_id')
    if not spare_id:
        raise ServiceError('请选择备件')
    qty = int(data.get('quantity') or 0)
    if qty <= 0:
        raise ServiceError('数量必须大于 0')
    unit_price = float(data.get('unit_price') or 0)
    po = PurchaseOrder(
        spare_part_id=int(spare_id),
        quantity=qty,
        unit_price=unit_price,
        total=qty * unit_price,
        supplier_name=data.get('supplier', data.get('supplier_name', '')),
        operator=current_user_name,
        purchase_date=datetime.strptime(data['purchase_date'], '%Y-%m-%d').date() if data.get('purchase_date') else datetime.utcnow().date(),
        remark=data.get('remark', ''),
    )
    db.session.add(po)
    # 自动入库：找该备件第一条 stock 记录，或新增
    stock = SpareStock.query.filter_by(spare_part_id=int(spare_id)).first()
    if stock:
        stock.quantity = (stock.quantity or 0) + qty
    else:
        db.session.add(SpareStock(spare_part_id=int(spare_id), quantity=qty, location=data.get('location', '默认库位')))
    return po


@transaction
def create_sales_order(data, current_user_name):
    """销售出库"""
    spare_id = data.get('spare_part_id')
    if not spare_id:
        raise ServiceError('请选择备件')
    qty = int(data.get('quantity') or 0)
    if qty <= 0:
        raise ServiceError('数量必须大于 0')
    # 先锁定该备件的库存行（with_for_update 行锁防 TOCTOU 超扣；SQLite 下为 no-op），
    # 再基于已锁定的行校验库存，避免「校验-扣减」之间被并发抢走
    stocks = SpareStock.query.filter(
        SpareStock.spare_part_id == int(spare_id), SpareStock.quantity > 0
    ).order_by(SpareStock.id).with_for_update().all()
    total_stock = sum(st.quantity or 0 for st in stocks)
    if total_stock < qty:
        raise ServiceError(f'库存不足（当前 {total_stock}，需要 {qty}）')
    unit_price = float(data.get('unit_price') or 0)
    so = SalesOrder(
        spare_part_id=int(spare_id),
        quantity=qty,
        unit_price=unit_price,
        total=qty * unit_price,
        customer_id=int(data['customer_id']) if data.get('customer_id') else None,
        operator=current_user_name,
        sales_date=datetime.strptime(data['sales_date'], '%Y-%m-%d').date() if data.get('sales_date') else datetime.utcnow().date(),
        remark=data.get('remark', ''),
    )
    db.session.add(so)
    # 出库：FIFO 扣减
    remaining = qty
    for st in stocks:
        if remaining <= 0:
            break
        take = min(st.quantity, remaining)
        st.quantity -= take
        remaining -= take
    return so


@transaction
def delete_purchase_order(po_id):
    """删除采购单：冲销其入库数量（从库存扣回，按行锁防并发）"""
    po = PurchaseOrder.query.get_or_404(po_id)
    qty = po.quantity or 0
    if qty > 0:
        stock = SpareStock.query.filter_by(spare_part_id=po.spare_part_id)\
            .order_by(SpareStock.id).with_for_update().first()
        if stock:
            stock.quantity = max(0, (stock.quantity or 0) - qty)
    db.session.delete(po)


@transaction
def delete_sales_order(so_id):
    """删除销售单：把出库数量补回库存（按行锁防并发）"""
    so = SalesOrder.query.get_or_404(so_id)
    qty = so.quantity or 0
    if qty > 0:
        stock = SpareStock.query.filter_by(spare_part_id=so.spare_part_id)\
            .order_by(SpareStock.id).with_for_update().first()
        if stock:
            stock.quantity = (stock.quantity or 0) + qty
        else:
            db.session.add(SpareStock(spare_part_id=so.spare_part_id, quantity=qty, location='默认库位'))
    db.session.delete(so)
