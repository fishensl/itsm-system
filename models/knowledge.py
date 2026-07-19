# -*- coding: utf-8 -*-
"""知识库模型"""
from datetime import datetime
from models.base import db


# ============================
# 知识库
# ============================

class KnowledgeBase(db.Model):
    """知识库"""
    __tablename__ = 'knowledge_base'
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(256), nullable=False)
    category = db.Column(db.String(32), default='故障案例')    # 故障案例/设备手册/内部规范/巡检经验
    content = db.Column(db.Text, default='')
    tags = db.Column(db.String(256), default='')
    related_ticket_id = db.Column(db.Integer, db.ForeignKey('tickets.id'), nullable=True)
    related_fault_id = db.Column(db.Integer, db.ForeignKey('faults.id'), nullable=True)
    related_device_type = db.Column(db.String(64), default='')
    view_count = db.Column(db.Integer, default=0)
    helpful_count = db.Column(db.Integer, default=0)
    is_published = db.Column(db.Boolean, default=True)
    created_by = db.Column(db.String(64), default='')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    ticket_rel = db.relationship('Ticket', backref='knowledge_entries')
    fault_rel = db.relationship('Fault', backref='knowledge_entries')
    # V7 附件
    attachments = db.relationship(
        'KnowledgeAttachment', backref='knowledge',
        cascade='all, delete-orphan', lazy='dynamic',
    )


class KnowledgeAttachment(db.Model):
    """知识库附件（V7）"""
    __tablename__ = 'knowledge_attachments'
    id = db.Column(db.Integer, primary_key=True)
    knowledge_id = db.Column(db.Integer, db.ForeignKey('knowledge_base.id'), nullable=False, index=True)
    file_name = db.Column(db.String(256), default='')
    file_path = db.Column(db.String(512), default='')
    file_ext = db.Column(db.String(16), default='')
    file_size = db.Column(db.Integer, default=0)
    uploaded_by = db.Column(db.String(64), default='')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


