# -*- coding: utf-8 -*-
"""备件 / 库存 / 采购 / 销售单模型"""
from datetime import datetime
from models.base import db


# ============================
# 备件管理（四合一）
# ============================

class SparePart(db.Model):
    """备件档案"""
    __tablename__ = 'spare_parts'
    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(64), unique=True, default='')
    name = db.Column(db.String(128), nullable=False)
    category = db.Column(db.String(64), default='')
    specification = db.Column(db.String(128), default='')
    unit = db.Column(db.String(16), default='个')
    min_stock = db.Column(db.Integer, default=0)
    remark = db.Column(db.Text, default='')
    # V6 新增业务字段
    brand = db.Column(db.String(64), default='')             # 品牌
    model = db.Column(db.String(64), default='')             # 型号
    parameters = db.Column(db.Text, default='')              # 详细参数
    manufacturer = db.Column(db.String(64), default='')      # 厂家
    image_path = db.Column(db.String(512), default='')       # 备件图片
    serial_number = db.Column(db.String(128), default='')    # 序列号
    reference_price = db.Column(db.Float, default=0.0)       # 采购参考价
    warranty_months = db.Column(db.Integer, default=0)       # 保修期（月）
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class SpareStock(db.Model):
    """备件库存"""
    __tablename__ = 'spare_stocks'
    id = db.Column(db.Integer, primary_key=True)
    spare_part_id = db.Column(db.Integer, db.ForeignKey('spare_parts.id'), nullable=False, index=True)
    location = db.Column(db.String(128), default='')
    quantity = db.Column(db.Integer, default=0)
    unit_price = db.Column(db.Float, default=0.0)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    spare_part_rel = db.relationship('SparePart', backref='stocks')


class PurchaseOrder(db.Model):
    """采购入库单"""
    __tablename__ = 'purchase_orders'
    id = db.Column(db.Integer, primary_key=True)
    number = db.Column(db.String(64), default='')
    spare_part_id = db.Column(db.Integer, db.ForeignKey('spare_parts.id'), nullable=True)
    supplier_name = db.Column(db.String(128), default='')
    quantity = db.Column(db.Integer, default=0)
    unit_price = db.Column(db.Float, default=0.0)
    total = db.Column(db.Float, default=0.0)
    purchase_date = db.Column(db.Date, nullable=True)
    operator = db.Column(db.String(64), default='')
    remark = db.Column(db.Text, default='')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    spare_part_rel = db.relationship('SparePart', backref='purchases')


class SalesOrder(db.Model):
    """销售出库单"""
    __tablename__ = 'sales_orders'
    id = db.Column(db.Integer, primary_key=True)
    number = db.Column(db.String(64), default='')
    spare_part_id = db.Column(db.Integer, db.ForeignKey('spare_parts.id'), nullable=True)
    customer_id = db.Column(db.Integer, db.ForeignKey('customers.id'), nullable=True)
    quantity = db.Column(db.Integer, default=0)
    unit_price = db.Column(db.Float, default=0.0)
    total = db.Column(db.Float, default=0.0)
    sales_date = db.Column(db.Date, nullable=True)
    operator = db.Column(db.String(64), default='')
    invoice_number = db.Column(db.String(128), default='')
    remark = db.Column(db.Text, default='')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    spare_part_rel = db.relationship('SparePart', backref='sales')
    customer_rel = db.relationship('Customer', backref='sales_orders')


class StockMovement(db.Model):
    """库存流水（单一账本：采购/销售/冲销/盘点调整全部走此表，来源可追溯）"""
    __tablename__ = 'stock_movements'
    id = db.Column(db.Integer, primary_key=True)
    spare_part_id = db.Column(db.Integer, db.ForeignKey('spare_parts.id'), nullable=False, index=True)
    movement_type = db.Column(db.String(16), nullable=False)  # purchase/sales/purchase_cancel/sales_cancel/adjust
    quantity = db.Column(db.Integer, default=0)                # 正=入库 负=出库
    balance_after = db.Column(db.Integer, default=0)           # 变动后该备件总库存
    location = db.Column(db.String(128), default='')
    source_id = db.Column(db.Integer, default=None)            # 关联单据 id（采购/销售/库存行）
    operator = db.Column(db.String(64), default='')
    remark = db.Column(db.Text, default='')
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)

    spare_part_rel = db.relationship('SparePart', backref='movements')


class SpareBorrow(db.Model):
    """备件借用（借出登记 → 归还回库；借出扣库存、归还回补，流水走 stock_movements）"""
    __tablename__ = 'spare_borrows'
    id = db.Column(db.Integer, primary_key=True)
    spare_part_id = db.Column(db.Integer, db.ForeignKey('spare_parts.id'), nullable=False, index=True)
    borrower = db.Column(db.String(64), nullable=False)       # 借用人
    borrower_phone = db.Column(db.String(32), default='')
    quantity = db.Column(db.Integer, nullable=False)          # 借出数量（>0）
    location = db.Column(db.String(128), default='')          # 出借库位
    borrow_date = db.Column(db.Date, default=datetime.utcnow().date, index=True)
    expected_return_date = db.Column(db.Date, nullable=True)  # 预计归还日
    return_date = db.Column(db.Date, nullable=True)           # 实际归还日
    status = db.Column(db.String(16), default='借用中', index=True)  # 借用中/已归还/逾期
    operator = db.Column(db.String(64), default='')           # 经办人
    remark = db.Column(db.Text, default='')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    spare_part_rel = db.relationship('SparePart', backref='borrows')


