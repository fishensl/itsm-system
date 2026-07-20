# -*- coding: utf-8 -*-
"""销售管线模型（商机/报价/合同/项目）"""
from datetime import datetime
from models.base import db


# ============================
# 销售管理
# ============================

class Opportunity(db.Model):
    """商机跟进"""
    __tablename__ = 'opportunities'
    id = db.Column(db.Integer, primary_key=True)
    customer_id = db.Column(db.Integer, db.ForeignKey('customers.id'), nullable=True)
    title = db.Column(db.String(256), nullable=False)
    stage = db.Column(db.String(32), default='初步接触')  # 初步接触/需求确认/方案报价/商务谈判/成交/失败
    expected_amount = db.Column(db.Float, default=0.0)
    expected_close_date = db.Column(db.Date, nullable=True)
    owner = db.Column(db.String(64), default='')
    remark = db.Column(db.Text, default='')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    customer_rel = db.relationship('Customer', backref='opportunities')


class Quotation(db.Model):
    """报价单"""
    __tablename__ = 'quotations'
    id = db.Column(db.Integer, primary_key=True)
    number = db.Column(db.String(64), default='')
    opportunity_id = db.Column(db.Integer, db.ForeignKey('opportunities.id'), nullable=True)
    customer_id = db.Column(db.Integer, db.ForeignKey('customers.id'), nullable=True)
    items_json = db.Column(db.Text, default='[]')
    total_amount = db.Column(db.Float, default=0.0)
    valid_until = db.Column(db.Date, nullable=True)
    status = db.Column(db.String(16), default='草稿')  # 草稿/已发送/已接受/已拒绝
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    opportunity_rel = db.relationship('Opportunity', backref='quotations')
    customer_rel = db.relationship('Customer', backref='quotations')


class Contract(db.Model):
    """合同管理"""
    __tablename__ = 'contracts'
    id = db.Column(db.Integer, primary_key=True)
    number = db.Column(db.String(64), default='')
    customer_id = db.Column(db.Integer, db.ForeignKey('customers.id'), nullable=True)
    opportunity_id = db.Column(db.Integer, db.ForeignKey('opportunities.id'), nullable=True)
    title = db.Column(db.String(256), nullable=False)
    amount = db.Column(db.Float, default=0.0)
    start_date = db.Column(db.Date, nullable=True)
    end_date = db.Column(db.Date, nullable=True)
    status = db.Column(db.String(32), default='执行中')  # 草签/已签/执行中/已完成/已终止
    file_path = db.Column(db.String(256), default='')
    content_json = db.Column(db.Text, default='{}')
    # v3 新增：巡检自动生成配置
    inspection_frequency = db.Column(db.String(32), default='')  # ''/每月/每季度/每半年/每年
    inspection_template_id = db.Column(db.Integer, db.ForeignKey('inspection_templates.id'), nullable=True)  # 旧模板（只读回退，勿再写入）
    # 新任务模板（v1.1 起自动巡检链路的主引用；旧 inspection_template_id 经迁移 a8b9c0d1e2f3 按名匹配回填）
    task_template_id = db.Column(db.Integer, db.ForeignKey('inspection_task_templates.id'),
                                 nullable=True, index=True)
    last_generated_date = db.Column(db.Date, nullable=True)       # 上次生成日，防重复
    auto_generate_tasks = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    customer_rel = db.relationship('Customer', backref='contracts')
    opportunity_rel = db.relationship('Opportunity', backref='contracts')
    template_rel = db.relationship('InspectionTemplate', backref='contracts_with_template')
    task_template_rel = db.relationship('InspectionTaskTemplate', backref='contracts_with_task_template')


class Project(db.Model):
    """项目管理"""
    __tablename__ = 'projects'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(256), nullable=False)
    contract_id = db.Column(db.Integer, db.ForeignKey('contracts.id'), nullable=True)
    customer_id = db.Column(db.Integer, db.ForeignKey('customers.id'), nullable=True)
    manager = db.Column(db.String(64), default='')
    start_date = db.Column(db.Date, nullable=True)
    end_date = db.Column(db.Date, nullable=True)
    status = db.Column(db.String(32), default='未启动')  # 未启动/进行中/已完成/已暂停
    progress = db.Column(db.Integer, default=0)
    budget = db.Column(db.Float, default=0.0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    contract_rel = db.relationship('Contract', backref='projects')
    customer_rel = db.relationship('Customer', backref='projects')


