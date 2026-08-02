# -*- coding: utf-8 -*-
"""操作审计日志模型（P4 审计查询页）"""
from datetime import datetime

from models.base import db


class AuditLog(db.Model):
    """敏感操作审计：写表 + 日志双写，admin 可查询"""
    __tablename__ = 'audit_logs'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True, index=True)
    username = db.Column(db.String(64), default='', index=True)
    action = db.Column(db.String(64), default='', index=True)   # 如 device:delete / device:reveal
    target_type = db.Column(db.String(32), default='')          # device/ticket/customer/backup...
    target_id = db.Column(db.Integer, nullable=True)
    detail = db.Column(db.String(512), default='')
    ip = db.Column(db.String(64), default='')
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)
