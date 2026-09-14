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
    # 企业微信使用 {"webhook_url_encrypted":..}；其他渠道使用各自加密凭据。
    config_json = db.Column(db.Text, default='{}')
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


class CustomerNotifyBinding(db.Model):
    __tablename__ = 'customer_notify_bindings'
    id = db.Column(db.Integer, primary_key=True)
    customer_id = db.Column(db.Integer, db.ForeignKey('customers.id', ondelete='CASCADE'), nullable=False, index=True)
    name = db.Column(db.String(80), nullable=False, default='客户群')
    channel_type = db.Column(db.String(20), nullable=False, default='wecom')
    signing_secret_encrypted = db.Column(db.Text, nullable=False, default='')
    subscriptions_json = db.Column(db.Text, nullable=False, default='{}')
    quiet_start = db.Column(db.Integer, nullable=False, default=0)
    quiet_end = db.Column(db.Integer, nullable=False, default=0)
    digest_minutes = db.Column(db.Integer, nullable=False, default=0)
    next_send_at = db.Column(db.DateTime, nullable=True)
    inherit_to_children = db.Column(db.Boolean, nullable=False, default=False)  # 允许无独立群的下级客户共用本群
    webhook_encrypted = db.Column(db.Text, nullable=False, default='')
    fingerprint = db.Column(db.String(64), unique=True, nullable=True)
    enabled = db.Column(db.Boolean, nullable=False, default=False)
    version = db.Column(db.Integer, nullable=False, default=1)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class CustomerNotifyDelivery(db.Model):
    __tablename__ = 'customer_notify_deliveries'
    id = db.Column(db.Integer, primary_key=True)
    customer_id = db.Column(db.Integer, nullable=False, index=True)
    event_key = db.Column(db.String(180), nullable=False, unique=True)
    event_type = db.Column(db.String(48), nullable=False)
    binding_version = db.Column(db.Integer, nullable=False)
    status = db.Column(db.String(24), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class NotificationEvent(db.Model):
    __tablename__ = 'notification_events'
    id = db.Column(db.String(36), primary_key=True)
    dedupe_key = db.Column(db.String(200), nullable=False, unique=True)
    event_type = db.Column(db.String(64), nullable=False)
    audience = db.Column(db.String(16), nullable=False)
    customer_id = db.Column(db.Integer, nullable=True, index=True)
    entity_type = db.Column(db.String(24), nullable=False, default='')
    entity_id = db.Column(db.Integer, nullable=True)
    payload_json = db.Column(db.Text, nullable=False)
    template_version = db.Column(db.Integer, nullable=False, default=1)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, index=True)
    expires_at = db.Column(db.DateTime, nullable=False)
    confirmed_by = db.Column(db.Integer, nullable=True)
    confirmed_at = db.Column(db.DateTime, nullable=True)
    feedback = db.Column(db.String(500), nullable=False, default='')


class NotificationDelivery(db.Model):
    __tablename__ = 'notification_deliveries'
    id = db.Column(db.Integer, primary_key=True)
    event_id = db.Column(db.String(36), db.ForeignKey('notification_events.id', ondelete='CASCADE'), nullable=False, index=True)
    target_key = db.Column(db.String(80), nullable=False)
    binding_id = db.Column(db.Integer, nullable=True)
    binding_version = db.Column(db.Integer, nullable=True)
    channel_type = db.Column(db.String(24), nullable=False)
    user_id = db.Column(db.Integer, nullable=True)
    config_fingerprint = db.Column(db.String(64), nullable=True)
    status = db.Column(db.String(24), nullable=False, index=True)
    attempts = db.Column(db.Integer, nullable=False, default=0)
    next_attempt_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, index=True)
    lease_until = db.Column(db.DateTime, nullable=True)
    lease_token = db.Column(db.String(36), nullable=True)
    error_code = db.Column(db.String(64), nullable=False, default='')
    finished_at = db.Column(db.DateTime, nullable=True)
    __table_args__ = (db.UniqueConstraint('event_id', 'target_key', name='uq_notification_event_target'),)


class NotificationAttempt(db.Model):
    __tablename__ = 'notification_attempts'
    id = db.Column(db.Integer, primary_key=True)
    delivery_id = db.Column(db.Integer, db.ForeignKey('notification_deliveries.id', ondelete='CASCADE'), nullable=False, index=True)
    number = db.Column(db.Integer, nullable=False)
    result = db.Column(db.String(24), nullable=False)
    error_code = db.Column(db.String(64), nullable=False, default='')
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)


class NotificationPreference(db.Model):
    __tablename__ = 'notification_preferences'
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), primary_key=True)
    daily_digest = db.Column(db.Boolean, nullable=False, default=False)
    weekly_digest = db.Column(db.Boolean, nullable=False, default=False)
    reminders = db.Column(db.Boolean, nullable=False, default=True)


class NotificationWorkerState(db.Model):
    __tablename__ = 'notification_worker_states'
    id = db.Column(db.String(40), primary_key=True)
    heartbeat_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
