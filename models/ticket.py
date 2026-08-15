# -*- coding: utf-8 -*-
"""工单 / 故障模型"""
from datetime import datetime
from models.base import db
from utils.constants import TICKET_PENDING_ASSIGN


# ============================
# 故障 / 工单管理
# ============================

class FaultType(db.Model):
    """故障类型（三级分级分类：一级 parent_id 为空，二级/三级通过 parent_id 挂载）"""
    __tablename__ = 'fault_types'
    # 组合唯一：同级下分类名唯一（三级树中不同父级可重名，如多个二级下均有「DNS/DHCP服务」）
    __table_args__ = (
        db.UniqueConstraint('name', 'parent_id', name='uq_fault_types_name_parent'),
    )
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(64), nullable=False)
    parent_id = db.Column(db.Integer, db.ForeignKey('fault_types.id'), nullable=True, index=True)
    level = db.Column(db.Integer, default=1)
    sort_order = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class Ticket(db.Model):
    """工单"""
    __tablename__ = 'tickets'
    id = db.Column(db.Integer, primary_key=True)
    number = db.Column(db.String(32), nullable=False, unique=True, index=True)  # WO-20260610-001
    source_type = db.Column(db.String(32), default='手动创建')     # 客户报修/巡检发现/手动创建/定期维护
    priority = db.Column(db.String(16), default='中', index=True)
    status = db.Column(db.String(32), default=TICKET_PENDING_ASSIGN, index=True)
    title = db.Column(db.String(256), nullable=False)
    description = db.Column(db.Text, default='')
    customer_id = db.Column(db.Integer, db.ForeignKey('customers.id'), nullable=True, index=True)
    customer_name_text = db.Column(db.String(128), default='')  # 外网建单手填客户名（无客户主数据绑定）
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
    sla_deadline = db.Column(db.DateTime, nullable=True)  # S6: 按优先级计算的 SLA 截止时间
    report_file = db.Column(db.String(256), default='')
    created_by = db.Column(db.String(64), default='')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    # v3 新增：结构化故障字段（为向量化准备）
    fault_category_level1 = db.Column(db.String(64), default='')  # 硬件故障/软件故障/网络故障/安全事件/配置变更/环境问题
    fault_category_level2 = db.Column(db.String(64), default='')  # 子分类
    fault_category_level3 = db.Column(db.String(64), default='')  # 三级分类（对齐 Fault）
    symptoms_json = db.Column(db.Text, default='[]')               # [{"symptom":"...","detail":"...","duration":"..."}]
    affected_components_json = db.Column(db.Text, default='[]')    # [{"component":"...","role":"...","impact":"..."}]
    resolution_steps_json = db.Column(db.Text, default='[]')       # [{"step":1,"action":"...","result":"..."}]
    root_cause_category = db.Column(db.String(64), default='')    # 配置错误/硬件老化/软件BUG/人为失误/外部攻击/电力故障
    severity_level = db.Column(db.String(16), default='')          # P1/P2/P3/P4
    impact_scope = db.Column(db.String(128), default='')          # 影响范围
    normalized_tags = db.Column(db.String(256), default='')       # 标准化标签（逗号分隔）

    # V28: 合同例外审批（客户合同过期时创建需部门主管审核）
    contract_exception_status = db.Column(db.String(16), default='')  # ''/待审核/通过/拒绝
    contract_exception_reason = db.Column(db.Text, default='')
    contract_exception_by = db.Column(db.String(64), default='')
    contract_exception_at = db.Column(db.DateTime, nullable=True)
    # V28: 工单挂起（采购等待/不可处置等暂停处置时效）
    suspended_at = db.Column(db.DateTime, nullable=True)
    suspended_seconds = db.Column(db.Integer, default=0)      # 累计挂起秒数（SLA 顺延用）
    suspend_timeout_notified_at = db.Column(db.DateTime, nullable=True)  # 挂起超时提醒去重

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


class TicketSuspend(db.Model):
    """工单挂起段（采购等待/无法处置暂停处置时效，恢复时累计时长并顺延 SLA）"""
    __tablename__ = 'ticket_suspends'
    id = db.Column(db.Integer, primary_key=True)
    ticket_id = db.Column(db.Integer, db.ForeignKey('tickets.id'), nullable=False, index=True)
    reason = db.Column(db.Text, default='')
    started_at = db.Column(db.DateTime, nullable=True)
    ended_at = db.Column(db.DateTime, nullable=True)
    operator = db.Column(db.String(64), default='')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    ticket_rel = db.relationship('Ticket', backref='suspends')


class TicketProgress(db.Model):
    """工单处置进展（工程师/主管按规范填写进展 + 现场照片）"""
    __tablename__ = 'ticket_progresses'
    id = db.Column(db.Integer, primary_key=True)
    ticket_id = db.Column(db.Integer, db.ForeignKey('tickets.id'), nullable=False, index=True)
    content = db.Column(db.Text, default='')
    photos_json = db.Column(db.Text, default='[]')   # [相对 static 路径, ...]
    operator = db.Column(db.String(64), default='')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    ticket_rel = db.relationship('Ticket', backref='progresses')


class CustomerContractReview(db.Model):
    """客户合同例外申请（过期客户安排任务时部门主管审核）"""
    __tablename__ = 'customer_contract_reviews'
    id = db.Column(db.Integer, primary_key=True)
    customer_id = db.Column(db.Integer, db.ForeignKey('customers.id'), nullable=False, index=True)
    requester_user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    reason = db.Column(db.Text, default='')
    status = db.Column(db.String(16), default='')   # ''/待审核/通过/拒绝
    reviewed_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    reviewed_at = db.Column(db.DateTime, nullable=True)
    review_comment = db.Column(db.Text, default='')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    customer_rel = db.relationship('Customer', backref='contract_reviews')
    requester_rel = db.relationship('User', foreign_keys=[requester_user_id],
                                    backref='contract_review_requests')
    reviewer_rel = db.relationship('User', foreign_keys=[reviewed_by],
                                   backref='contract_review_done')


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
    fault_category_level3 = db.Column(db.String(64), default='')
    symptoms_json = db.Column(db.Text, default='[]')
    affected_components_json = db.Column(db.Text, default='[]')
    resolution_steps_json = db.Column(db.Text, default='[]')
    root_cause_category = db.Column(db.String(64), default='')
    severity_level = db.Column(db.String(16), default='')
    impact_scope = db.Column(db.String(128), default='')
    normalized_tags = db.Column(db.String(256), default='')

    customer_rel = db.relationship('Customer', backref='faults')

