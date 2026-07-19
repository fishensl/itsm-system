# -*- coding: utf-8 -*-
"""AI 配置 / 配置备份 / 拓扑 / 采集任务模型"""
from datetime import datetime
from models.base import db


# ============================
# AI 对接 + 设备扩展
# ============================

class AIConfig(db.Model):
    """AI 对接配置"""
    __tablename__ = 'ai_config'
    id = db.Column(db.Integer, primary_key=True)
    provider = db.Column(db.String(32), default='OpenAI')      # OpenAI/Anthropic/Ollama/自定义
    api_endpoint = db.Column(db.String(256), default='')
    api_key_encrypted = db.Column(db.Text, default='')
    model_name = db.Column(db.String(64), default='gpt-4')
    max_tokens = db.Column(db.Integer, default=2048)
    temperature = db.Column(db.Float, default=0.7)
    inspection_prompt_template = db.Column(db.Text, default='')
    fault_prompt_template = db.Column(db.Text, default='')
    is_enabled = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class DeviceConfigBackup(db.Model):
    """设备配置备份"""
    __tablename__ = 'device_config_backups'
    id = db.Column(db.Integer, primary_key=True)
    device_id = db.Column(db.Integer, db.ForeignKey('devices.id'), nullable=False, index=True)
    backup_type = db.Column(db.String(32), default='运行配置')   # 启动配置/运行配置/全部配置
    config_content = db.Column(db.Text, default='')
    backup_method = db.Column(db.String(32), default='手动输入')  # 自动抓取/手动输入/文件上传/SSH采集/Telnet采集/SNMP采集
    backup_date = db.Column(db.Date, nullable=True)
    file_path = db.Column(db.String(256), default='')
    checksum = db.Column(db.String(64), default='')
    created_by = db.Column(db.String(64), default='')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    device_rel = db.relationship('Device', backref='config_backups')


class Topology(db.Model):
    """网络拓扑图"""
    __tablename__ = 'topologies'
    id = db.Column(db.Integer, primary_key=True)
    customer_id = db.Column(db.Integer, db.ForeignKey('customers.id'), nullable=True)
    region_id = db.Column(db.Integer, db.ForeignKey('regions.id'), nullable=True)
    name = db.Column(db.String(256), nullable=False)
    description = db.Column(db.Text, default='')
    file_path = db.Column(db.String(512), default='')
    file_type = db.Column(db.String(32), default='image')    # visio/image/pdf/other
    upload_by = db.Column(db.String(64), default='')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    # V20: 在线拓扑（drawio 集成）
    diagram_xml = db.Column(db.Text, default='')             # mxGraph XML（在线图源数据；上传图为空）
    source = db.Column(db.String(16), default='upload')      # upload | draw
    thumbnail_path = db.Column(db.String(512), default='')   # 在线图缩略图 PNG（列表预览用）
    pdf_path = db.Column(db.String(512), default='')         # 在线图自动导出的 PDF（快速下载）
    vsdx_path = db.Column(db.String(512), default='')        # 在线图自动导出的 VSDX（快速下载）
    svg_path = db.Column(db.String(512), default='')         # 在线图自动导出的 SVG（矢量预览）
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    customer_rel = db.relationship('Customer', backref='topologies')
    region_rel = db.relationship('Region', backref='topologies')


class DeviceCollectTask(db.Model):
    """设备远程采集任务"""
    __tablename__ = 'device_collect_tasks'
    id = db.Column(db.Integer, primary_key=True)
    task_type = db.Column(db.String(32), default='配置备份')   # 配置备份/状态采集/SNMP巡检
    device_id = db.Column(db.Integer, db.ForeignKey('devices.id'), nullable=False, index=True)
    protocol = db.Column(db.String(16), default='SSH')        # SSH/Telnet/SNMPv2c/SNMPv3
    commands_json = db.Column(db.Text, default='[]')
    snmp_oids_json = db.Column(db.Text, default='[]')
    status = db.Column(db.String(16), default='pending')       # pending/running/success/failed
    result_json = db.Column(db.Text, default='{}')
    error_message = db.Column(db.Text, default='')
    started_at = db.Column(db.DateTime, nullable=True)
    completed_at = db.Column(db.DateTime, nullable=True)
    created_by = db.Column(db.String(64), default='')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    device_rel = db.relationship('Device', backref='collect_tasks')


