# -*- coding: utf-8 -*-
"""多渠道通知平台配置（企微/钉钉/飞书等可插拔渠道 + 事件通知规则）"""
from datetime import datetime
from models.base import db


class NotifyChannelConfig(db.Model):
    """通知渠道配置（一个渠道一条；config_json 敏感项 Fernet 加密）"""
    __tablename__ = 'notify_channel_configs'
    id = db.Column(db.Integer, primary_key=True)
    channel_type = db.Column(db.String(32), nullable=False, unique=True)  # wecom/dingtalk/feishu
    name = db.Column(db.String(64), default='')
    config_json = db.Column(db.Text, default='{}')       # {"corpid":..,"agent_id":..,"secret_encrypted":..}
    is_enabled = db.Column(db.Boolean, default=False)
    sort_order = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class NotifyRule(db.Model):
    """事件通知规则（通知类型 → 接收角色/指定用户；规则与渠道解耦）"""
    __tablename__ = 'notify_rules'
    id = db.Column(db.Integer, primary_key=True)
    event_type = db.Column(db.String(32), nullable=False, unique=True)
    label = db.Column(db.String(128), default='')
    is_enabled = db.Column(db.Boolean, default=True)
    recipients_json = db.Column(db.Text, default='{}')   # {"roles":["operator"],"users":[1,2]}
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
