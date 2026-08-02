# -*- coding: utf-8 -*-
"""系统配置（key-value 单例，P4 界面版本切换等）"""
from datetime import datetime

from models.base import db


class SystemSetting(db.Model):
    """系统级键值配置"""
    __tablename__ = 'system_settings'
    key = db.Column(db.String(64), primary_key=True)
    value = db.Column(db.Text, default='')
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
