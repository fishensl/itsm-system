# -*- coding: utf-8 -*-
"""站内通知模型（P3 通知中心）"""
from datetime import datetime

from models.base import db


class Notification(db.Model):
    """站内通知：工单派单/审核结果/库存预警等事件源写入，用户已读跟踪"""
    __tablename__ = 'notifications'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    category = db.Column(db.String(32), default='system')  # ticket/inspection/spare/system
    title = db.Column(db.String(128), default='')
    content = db.Column(db.Text, default='')
    link = db.Column(db.String(256), default='')            # 跳转路径（/app/tickets/3 或 /tickets/3）
    is_read = db.Column(db.Boolean, default=False, index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)

    user_rel = db.relationship('User', backref='notifications')
