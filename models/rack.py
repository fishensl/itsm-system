# -*- coding: utf-8 -*-
"""机柜模型"""
from datetime import datetime
from models.base import db


# ============================
# 机柜管理（V6.1）
# ============================

class Rack(db.Model):
    """机柜（直接归属客户）"""
    __tablename__ = 'racks'
    id = db.Column(db.Integer, primary_key=True)
    customer_id = db.Column(db.Integer, db.ForeignKey('customers.id'), nullable=True, index=True)
    name = db.Column(db.String(64), nullable=False)         # 机柜编号/名称
    total_u = db.Column(db.Integer, default=42)             # 总 U 数
    color = db.Column(db.String(16), default='#0d6efd')     # 显示颜色
    pdu_total_w = db.Column(db.Integer, default=0)          # PDU 额定总功率（W）
    remark = db.Column(db.Text, default='')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    customer_rel = db.relationship('Customer', backref='racks')


class RackInstall(db.Model):
    """设备上架记录（在机柜中的位置）"""
    __tablename__ = 'rack_installs'
    id = db.Column(db.Integer, primary_key=True)
    rack_id = db.Column(db.Integer, db.ForeignKey('racks.id'), nullable=False, index=True)
    device_id = db.Column(db.Integer, db.ForeignKey('devices.id'), nullable=True, index=True)  # 关联到设备表
    # 当 device_id 为空时表示手动录入（机柜中存在但不在主设备表的设备）
    manual_name = db.Column(db.String(128), default='')     # 手动设备名
    manual_brand = db.Column(db.String(64), default='')
    manual_model = db.Column(db.String(64), default='')
    manual_ip = db.Column(db.String(64), default='')
    start_u = db.Column(db.Integer, default=1)              # 起始 U 位（从 1 开始）
    occupy_u = db.Column(db.Integer, default=1)             # 占用 U 数
    rated_w = db.Column(db.Integer, default=0)              # 额定功耗（W）
    remark = db.Column(db.Text, default='')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    rack_rel = db.relationship('Rack', backref='installs')
    device_rel = db.relationship('Device', backref='rack_installs')
