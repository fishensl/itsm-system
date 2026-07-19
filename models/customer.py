# -*- coding: utf-8 -*-
"""地区 / 客户模型"""
from datetime import datetime
from models.base import db


# ============================
# 地区管理
# ============================

class Region(db.Model):
    """地区树"""
    __tablename__ = 'regions'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(128), nullable=False)
    parent_id = db.Column(db.Integer, db.ForeignKey('regions.id'), nullable=True)
    sort_order = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    parent = db.relationship('Region', remote_side='Region.id', backref='children')


# ============================
# 客户管理
# ============================

class Customer(db.Model):
    """客户"""
    __tablename__ = 'customers'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(128), nullable=False, unique=True, index=True)
    contact_person = db.Column(db.String(64), default='')
    phone = db.Column(db.String(32), default='', index=True)
    email = db.Column(db.String(128), default='')
    region_id = db.Column(db.Integer, db.ForeignKey('regions.id'), nullable=True)
    category_id = db.Column(db.Integer, db.ForeignKey('customer_categories.id'), nullable=True)  # 单位类别
    parent_id = db.Column(db.Integer, db.ForeignKey('customers.id'), nullable=True, index=True)  # 手动指定上级单位（空=按地区+类别自动推导）
    city = db.Column(db.String(64), default='')
    address = db.Column(db.String(256), default='')
    office = db.Column(db.String(128), default='')          # 办公室
    level = db.Column(db.String(32), default='常规', index=True)  # 核心/重点/常规（自动计算，可手动覆盖）
    has_onsite = db.Column(db.Boolean, default=False)      # 有无驻场
    onsite_contact = db.Column(db.String(64), default='')   # 驻场联系人
    onsite_phone = db.Column(db.String(32), default='')     # 驻场联系方式
    onsite_office = db.Column(db.String(128), default='')   # 驻场办公室
    has_drill = db.Column(db.Boolean, default=False)       # 有无攻防演练
    inspection_frequency = db.Column(db.String(16), default='')  # 巡检频率
    last_generated_date = db.Column(db.Date, nullable=True)  # V17: 客户频率自动任务最近一次生成到的期次起点
    device_count = db.Column(db.Integer, default=0)        # 关联设备数（冗余快照）
    source = db.Column(db.String(64), default='')           # 转介绍/展会/线上/其他
    remark = db.Column(db.Text, default='')
    extra_fields = db.Column(db.Text, default='')           # 自定义字段值（JSON 字符串 {字段名: 值}）
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    region_rel = db.relationship('Region', backref='customers', lazy=True)
    category_rel = db.relationship('CustomerCategory', backref='customers', lazy=True)
    parent = db.relationship('Customer', remote_side='Customer.id', backref='children')
    devices = db.relationship('Device', backref='customer', lazy='dynamic',
                              cascade='all, delete-orphan')


