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


# ============================
# 提交版本（巡检记录 / 工单通用审核闭环）
# ============================

class SubmissionVersion(db.Model):
    """提交版本 — 每次"上传报告+提交审核"追加一条，审核结果/意见挂在版本上。

    entity_type: inspection | ticket（entity_id 指向 inspections.id / tickets.id）
    同一实体 version_no 从 1 递增，形成"提交→审核→退回→再提交"完整可复查历史：
    每个版本保留报告文件、提交快照（content_json）、提交人/时间、审核人/时间/意见。
    """
    __tablename__ = 'submission_versions'
    id = db.Column(db.Integer, primary_key=True)
    entity_type = db.Column(db.String(16), default='inspection')
    entity_id = db.Column(db.Integer)
    version_no = db.Column(db.Integer, default=1)
    report_file = db.Column(db.String(256), default='')     # 该版上传的报告文件（相对 static 路径）
    content_json = db.Column(db.Text, default='{}')         # 该版提交快照（巡检:{conclusion}; 工单:{diagnosis,solution}）
    submitted_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    submitted_at = db.Column(db.DateTime, default=datetime.utcnow)
    review_status = db.Column(db.String(16), default='', index=True)   # ''(未审)/待审核/已通过/已退回
    reviewed_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    reviewed_at = db.Column(db.DateTime, nullable=True)
    review_comment = db.Column(db.Text, default='')          # 本轮审核意见（退回原因）
    revision_requirements = db.Column(db.Text, default='')   # 退回修改：需要修改的内容（与原因分行保存）
    review_checklist_json = db.Column(db.Text, default='{}') # 本轮审核检查项勾选 {"项名": "合格|需修改|不适用"}（未勾选项=未核对）
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    __table_args__ = (
        db.UniqueConstraint('entity_type', 'entity_id', 'version_no',
                            name='uq_submission_versions_entity_version'),
        db.Index('ix_submission_versions_entity', 'entity_type', 'entity_id'),
    )

    submitter_rel = db.relationship('User', foreign_keys=[submitted_by], backref='submitted_versions')
    reviewer_rel = db.relationship('User', foreign_keys=[reviewed_by], backref='reviewed_versions')


class SubmissionAsset(db.Model):
    """提交资料 — 每轮提交（SubmissionVersion）附带的各类资料明细。

    asset_type: report/config_zip/config_text/topology/asset_list
    - 正常提交：file_path 指向文件（config_text 另存 content_text 供在线查看）；
    - 必传项无法上传时：skip_reason 填豁免原因，file_path 为空；
    - target_id：同步目标 ID（DeviceConfigBackup.id / Topology.id），用于溯源。
    """
    __tablename__ = 'submission_assets'
    id = db.Column(db.Integer, primary_key=True)
    version_id = db.Column(db.Integer, db.ForeignKey('submission_versions.id'), nullable=False, index=True)
    asset_type = db.Column(db.String(32), default='report', index=True)
    file_path = db.Column(db.String(256), default='')
    file_name = db.Column(db.String(256), default='')
    device_id = db.Column(db.Integer, db.ForeignKey('devices.id'), nullable=True)
    content_text = db.Column(db.Text, default='')          # 文本配置内容（在线查看）
    target_id = db.Column(db.Integer, nullable=True)       # 同步目标 ID
    skip_reason = db.Column(db.Text, default='')           # 必传项豁免原因
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    version_rel = db.relationship('SubmissionVersion', backref='assets')
    device_rel = db.relationship('Device', backref='submission_assets')


# ============================
# 一次性导出文件（V24 导出筛选）
# ============================

class ExportFile(db.Model):
    """一次性导出文件（巡检/工单 bundle zip、设备密码包共用）

    - token：随机 UUID，下载端点凭证，GET 后即删（downloaded_at 标记 + 文件删除）
    - file_password_encrypted：密码包专用（Fernet 加密的 zip 密码，下载时经
      X-Export-Password 响应头一次性下发）
    """
    __tablename__ = 'export_files'
    id = db.Column(db.Integer, primary_key=True)
    token = db.Column(db.String(64), unique=True, nullable=False, index=True)
    file_path = db.Column(db.String(512), default='')      # 相对项目根路径（reports/exports/xxx.zip）
    download_name = db.Column(db.String(256), default='')  # 下载时文件名
    created_by_user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True, index=True)
    file_password_encrypted = db.Column(db.Text, default='')
    expires_at = db.Column(db.DateTime, nullable=True)
    downloaded_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    creator_rel = db.relationship('User', backref='export_files')


