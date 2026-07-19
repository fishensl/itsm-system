# -*- coding: utf-8 -*-
"""工单 / 故障模型"""
from datetime import datetime
from models.base import db


# ============================
# 故障 / 工单管理
# ============================

class FaultType(db.Model):
    """故障类型"""
    __tablename__ = 'fault_types'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(64), unique=True, nullable=False)
    sort_order = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class Ticket(db.Model):
    """工单"""
    __tablename__ = 'tickets'
    id = db.Column(db.Integer, primary_key=True)
    number = db.Column(db.String(32), nullable=False, unique=True, index=True)  # WO-20260610-001
    source_type = db.Column(db.String(32), default='手动创建')     # 客户报修/巡检发现/手动创建/定期维护
    priority = db.Column(db.String(16), default='中', index=True)
    status = db.Column(db.String(32), default='待派单', index=True)            # 待派单/待接单/处理中/待审核/待验收/已完成/已关闭
    title = db.Column(db.String(256), nullable=False)
    description = db.Column(db.Text, default='')
    customer_id = db.Column(db.Integer, db.ForeignKey('customers.id'), nullable=True, index=True)
    reporter = db.Column(db.String(64), default='')
    reporter_phone = db.Column(db.String(32), default='')
    related_inspection_id = db.Column(db.Integer, db.ForeignKey('inspections.id'), nullable=True)
    related_device_id = db.Column(db.Integer, db.ForeignKey('devices.id'), nullable=True)
    fault_category_id = db.Column(db.Integer, db.ForeignKey('fault_types.id'), nullable=True)
    assigned_to = db.Column(db.String(64), default='', index=True)
    assigned_by = db.Column(db.String(64), default='')
    assigned_at = db.Column(db.DateTime, nullable=True)
    accepted_at = db.Column(db.DateTime, nullable=True)
    started_at = db.Column(db.DateTime, nullable=True)
    completed_at = db.Column(db.DateTime, nullable=True)
    diagnosis = db.Column(db.Text, default='')
    solution = db.Column(db.Text, default='')
    result = db.Column(db.String(32), default='')
    audit_status = db.Column(db.String(16), default='')
    audit_by = db.Column(db.String(64), default='')
    audit_at = db.Column(db.DateTime, nullable=True)
    audit_comment = db.Column(db.Text, default='')
    accept_status = db.Column(db.String(16), default='')
    accept_by = db.Column(db.String(64), default='')
    accept_at = db.Column(db.DateTime, nullable=True)
    accept_comment = db.Column(db.Text, default='')
    service_duration = db.Column(db.Integer, default=0)
    report_file = db.Column(db.String(256), default='')
    created_by = db.Column(db.String(64), default='')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    # v3 新增：结构化故障字段（为向量化准备）
    fault_category_level1 = db.Column(db.String(64), default='')  # 硬件故障/软件故障/网络故障/安全事件/配置变更/环境问题
    fault_category_level2 = db.Column(db.String(64), default='')  # 子分类
    symptoms_json = db.Column(db.Text, default='[]')               # [{"symptom":"...","detail":"...","duration":"..."}]
    affected_components_json = db.Column(db.Text, default='[]')    # [{"component":"...","role":"...","impact":"..."}]
    resolution_steps_json = db.Column(db.Text, default='[]')       # [{"step":1,"action":"...","result":"..."}]
    root_cause_category = db.Column(db.String(64), default='')    # 配置错误/硬件老化/软件BUG/人为失误/外部攻击/电力故障
    severity_level = db.Column(db.String(16), default='')          # P1/P2/P3/P4
    impact_scope = db.Column(db.String(128), default='')          # 影响范围
    normalized_tags = db.Column(db.String(256), default='')       # 标准化标签（逗号分隔）

    customer_rel = db.relationship('Customer', backref='tickets')
    inspection_rel = db.relationship('Inspection', backref='tickets')
    device_rel = db.relationship('Device', backref='tickets')
    fault_type_rel = db.relationship('FaultType', backref='tickets')


class TicketLog(db.Model):
    """工单日志"""
    __tablename__ = 'ticket_logs'
    id = db.Column(db.Integer, primary_key=True)
    ticket_id = db.Column(db.Integer, db.ForeignKey('tickets.id'), nullable=False, index=True)
    action = db.Column(db.String(32), default='')
    operator = db.Column(db.String(64), default='')
    comment = db.Column(db.Text, default='')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    ticket_rel = db.relationship('Ticket', backref='logs')


# 保留旧 Fault 模型（兼容现有数据，逐步被 Ticket 取代）
class Fault(db.Model):
    """故障处理记录（旧）"""
    __tablename__ = 'faults'
    id = db.Column(db.Integer, primary_key=True)
    customer_id = db.Column(db.Integer, db.ForeignKey('customers.id'), nullable=True)
    ticket_id = db.Column(db.Integer, db.ForeignKey('tickets.id'), nullable=True)
    title = db.Column(db.String(128), nullable=False)
    handler = db.Column(db.String(64), default='')
    fault_time = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    fault_type = db.Column(db.String(64), default='')
    fault_description = db.Column(db.Text, default='')
    impact_range = db.Column(db.String(256), default='')
    fault_cause = db.Column(db.Text, default='')
    solution = db.Column(db.Text, default='')
    result = db.Column(db.String(32), default='已解决')
    recovery_time = db.Column(db.DateTime, nullable=True)
    report_file = db.Column(db.String(256), default='')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    # v3 新增：结构化故障字段（与 Ticket 一致，为向量化准备）
    fault_category_level1 = db.Column(db.String(64), default='')
    fault_category_level2 = db.Column(db.String(64), default='')
    symptoms_json = db.Column(db.Text, default='[]')
    affected_components_json = db.Column(db.Text, default='[]')
    resolution_steps_json = db.Column(db.Text, default='[]')
    root_cause_category = db.Column(db.String(64), default='')
    severity_level = db.Column(db.String(16), default='')
    impact_scope = db.Column(db.String(128), default='')
    normalized_tags = db.Column(db.String(256), default='')

    customer_rel = db.relationship('Customer', backref='faults')


