# -*- coding: utf-8 -*-
"""设备及其附属模型（固件/凭证/接口/字典/密码历史）"""
from datetime import datetime
from models.base import db


# ============================
# 设备管理（扩展自 Password 项目）
# ============================

class Device(db.Model):
    """网络设备"""
    __tablename__ = 'devices'
    __table_args__ = (
        db.Index('ix_devices_brand_model', 'brand', 'model'),  # 固件按品牌+型号匹配设备
    )
    id = db.Column(db.Integer, primary_key=True)
    customer_id = db.Column(db.Integer, db.ForeignKey('customers.id'), nullable=True, index=True)
    region_id = db.Column(db.Integer, db.ForeignKey('regions.id'), nullable=True)
    device_name = db.Column(db.String(128), nullable=False)
    device_type = db.Column(db.String(64), default='')
    brand = db.Column(db.String(64), default='')
    model = db.Column(db.String(64), default='')
    serial_number = db.Column(db.String(128), default='')
    network_type = db.Column(db.String(64), default='')      # 内网/外网/DMZ
    ip_address = db.Column(db.String(64), default='', index=True)
    port = db.Column(db.Integer, default=22)
    login_method = db.Column(db.String(32), default='')
    username = db.Column(db.String(128), default='')
    password_encrypted = db.Column(db.Text, default='')
    location = db.Column(db.String(128), default='')
    interface = db.Column(db.Text, default='')  # JSON 数组字符串；曾 String(128) 在 SQLite 宽松、PG 严格校验长度会截断/报错，故改 Text
    os_version = db.Column(db.String(128), default='')
    rule_version = db.Column(db.String(128), default='')
    license_expiry = db.Column(db.Date, nullable=True, index=True)
    license_start = db.Column(db.Date, nullable=True)            # 授权开始日（与 license_expiry 配对显示"授权时间"）
    cert_expiry_date = db.Column(db.Date, nullable=True)     # 证书到期日
    is_maintenance = db.Column(db.Boolean, default=False)
    is_in_use = db.Column(db.Boolean, default=True, index=True)
    remark = db.Column(db.Text, default='')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    region_rel = db.relationship('Region', backref='devices', lazy=True)


class DeviceFirmware(db.Model):
    """设备固件版本库 (V12) — 按品牌+型号管理系统固件/规则库的最新版本与更新说明"""
    __tablename__ = 'device_firmwares'
    id = db.Column(db.Integer, primary_key=True)
    brand = db.Column(db.String(64), nullable=False, default='', index=True)        # 品牌
    model = db.Column(db.String(128), nullable=False, default='', index=True)       # 型号
    firmware_type = db.Column(db.String(32), nullable=False, default='系统固件')     # 系统固件 / 规则库 / BIOS / 其他
    version = db.Column(db.String(64), nullable=False, default='')                  # 版本号
    release_date = db.Column(db.Date, nullable=True)                                # 发布日期
    changelog = db.Column(db.Text, default='')                                      # 更新说明（支持 Markdown）
    download_url = db.Column(db.String(512), default='')                            # 下载地址
    file_size_mb = db.Column(db.Float, default=0)                                   # 文件大小 (MB)
    md5_checksum = db.Column(db.String(64), default='')                             # MD5 校验
    is_latest = db.Column(db.Boolean, default=False, index=True)                    # 是否最新推荐版本（同 brand+model+firmware_type 仅一条 true）
    min_compatible_hardware = db.Column(db.String(256), default='')                 # 最低硬件要求
    upgrade_guide = db.Column(db.Text, default='')                                  # 升级步骤
    remark = db.Column(db.Text, default='')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class DeviceCredential(db.Model):
    """设备多登录凭证"""
    __tablename__ = 'device_credentials'
    id = db.Column(db.Integer, primary_key=True)
    device_id = db.Column(db.Integer, db.ForeignKey('devices.id'), nullable=False, index=True)
    login_method = db.Column(db.String(32), default='SSH')
    username = db.Column(db.String(128), default='')
    password_encrypted = db.Column(db.Text, default='')
    status = db.Column(db.String(16), default='normal')  # normal/error
    password_history = db.Column(db.Text, default='[]')  # JSON
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    device_rel = db.relationship('Device', backref='credentials')


class DeviceInterface(db.Model):
    """设备接口信息"""
    __tablename__ = 'device_interfaces'
    id = db.Column(db.Integer, primary_key=True)
    device_id = db.Column(db.Integer, db.ForeignKey('devices.id'), nullable=False, index=True)
    name = db.Column(db.String(128), default='')
    status = db.Column(db.String(16), default='up')
    ip = db.Column(db.String(64), default='')
    peer_ip = db.Column(db.String(64), default='')
    description = db.Column(db.String(256), default='')

    device_rel = db.relationship('Device', backref='interfaces')


class CustomField(db.Model):
    """设备自定义字段"""
    __tablename__ = 'custom_fields'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(64), nullable=False)
    field_type = db.Column(db.String(16), default='text')  # text/date
    sort_order = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class PasswordHistory(db.Model):
    """设备密码修改历史"""
    __tablename__ = 'password_history'
    id = db.Column(db.Integer, primary_key=True)
    device_id = db.Column(db.Integer, db.ForeignKey('devices.id'), nullable=False, index=True)
    password_encrypted = db.Column(db.Text, default='')
    changed_by = db.Column(db.String(64), default='')
    remark = db.Column(db.String(256), default='')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    device_rel = db.relationship('Device', backref='password_histories')


class DeviceType(db.Model):
    """设备类型"""
    __tablename__ = 'device_types'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(64), unique=True, nullable=False)
    sort_order = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class DeviceSubType(db.Model):
    """设备细分类别（V5: 用于巡检模板匹配）"""
    __tablename__ = 'device_sub_types'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(64), unique=True, nullable=False)
    category = db.Column(db.String(32), default='')   # 服务器/网络设备/安全设备/环控设备/会议设备
    sort_order = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class NetworkType(db.Model):
    """网络类型"""
    __tablename__ = 'network_types'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(64), unique=True, nullable=False)
    sort_order = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class Brand(db.Model):
    """品牌"""
    __tablename__ = 'brands'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(64), unique=True, nullable=False)
    sort_order = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


