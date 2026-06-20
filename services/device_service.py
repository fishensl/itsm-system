# -*- coding: utf-8 -*-
"""Device 业务服务

支持两种调用风格：
- create_device_from_form(form_dict): web 路由用（接收 customer_id 整数）
- create_device(data): 旧式（接收 customer_name 字符串，内部查找）
"""
import re
import json
from datetime import datetime
from models import db, Device, Customer, SparePart, SpareStock
from utils.crypto import encrypt_password
from .base import ServiceError, transaction


# 简单的 IPv4 校验（仅用于提示，不强制）
IPV4_RE = re.compile(r'^(\d{1,3}\.){3}\d{1,3}$')


@transaction
def create_device_from_form(form):
    """新增设备（接收 web 表单 form 字典）

    表单字段：device_name/customer_id/region_id/device_type/brand/model/
              ip_address/port/username/password/serial_number/login_method/
              location/interface(多值)/os_version/rule_version/is_maintenance/
              is_in_use/license_expiry/remark
    """
    name = (form.get('device_name') or '').strip()
    if not name:
        raise ServiceError('设备名称不能为空')
    if Device.query.filter_by(device_name=name).first():
        raise ServiceError(f'设备 "{name}" 已存在')

    customer_id = form.get('customer_id')
    if customer_id:
        try:
            customer_id = int(customer_id)
        except (TypeError, ValueError):
            customer_id = None

    plain_password = form.get('password', '')
    encrypted = encrypt_password(plain_password) if plain_password else ''
    interfaces = [v.strip() for v in form.getlist('interface') if v.strip()] if hasattr(form, 'getlist') else []

    d = Device(
        customer_id=customer_id,
        region_id=int(form['region_id']) if form.get('region_id') else None,
        device_name=name,
        device_type=form.get('device_type', ''),
        brand=form.get('brand', ''),
        model=form.get('model', ''),
        ip_address=form.get('ip_address', ''),
        port=int(form.get('port', 22)),
        username=form.get('username', ''),
        password_encrypted=encrypted,
        serial_number=form.get('serial_number', ''),
        login_method=form.get('login_method', ''),
        location=form.get('location', ''),
        interface=json.dumps(interfaces, ensure_ascii=False) if interfaces else None,
        os_version=form.get('os_version', ''),
        rule_version=form.get('rule_version', ''),
        is_maintenance=form.get('is_maintenance') == 'on',
        is_in_use=form.get('is_in_use') == 'on',
        license_expiry=_parse_date(form.get('license_expiry')),
        remark=form.get('remark', ''),
    )
    db.session.add(d)
    return d


@transaction
def update_device_from_form(device_id, form):
    """更新设备（接收 web 表单 form 字典）

    密码变更时旧密码写入 PasswordHistory
    """
    d = Device.query.get_or_404(device_id)
    name = (form.get('device_name') or '').strip()
    if not name:
        raise ServiceError('设备名称不能为空')

    customer_id = form.get('customer_id')
    if customer_id:
        try:
            customer_id = int(customer_id)
        except (TypeError, ValueError):
            customer_id = d.customer_id
    else:
        customer_id = d.customer_id

    d.device_name = name
    d.customer_id = customer_id
    d.region_id = int(form['region_id']) if form.get('region_id') else d.region_id
    d.device_type = form.get('device_type', '')
    d.brand = form.get('brand', '')
    d.model = form.get('model', '')
    d.ip_address = form.get('ip_address', '')
    d.port = int(form.get('port', 22))
    d.username = form.get('username', '')
    plain_password = form.get('password', '')
    if plain_password:
        # 保存旧密码到历史
        if d.password_encrypted:
            from models import PasswordHistory
            history = PasswordHistory(
                device_id=d.id,
                password_encrypted=d.password_encrypted,
                changed_by=form.get('changed_by_name', ''),
                remark=form.get('pwd_remark', '')
            )
            db.session.add(history)
        d.password_encrypted = encrypt_password(plain_password)
    d.serial_number = form.get('serial_number', '')
    d.login_method = form.get('login_method', '')
    d.location = form.get('location', '')
    interfaces = [v.strip() for v in form.getlist('interface') if v.strip()] if hasattr(form, 'getlist') else []
    d.interface = json.dumps(interfaces, ensure_ascii=False) if interfaces else None
    d.os_version = form.get('os_version', '')
    d.rule_version = form.get('rule_version', '')
    d.is_maintenance = form.get('is_maintenance') == 'on'
    d.is_in_use = form.get('is_in_use') == 'on'
    d.license_expiry = _parse_date(form.get('license_expiry'))
    d.remark = form.get('remark', '')
    return d


@transaction
def delete_device(device_id):
    """删除设备（清理关联的密码历史、凭据、接口、配置备份、采集任务；置空工单/上架的设备引用）"""
    d = Device.query.get_or_404(device_id)
    from models import (PasswordHistory, DeviceCredential, DeviceInterface,
                        DeviceConfigBackup, DeviceCollectTask, Ticket, RackInstall)
    PasswordHistory.query.filter_by(device_id=device_id).delete()
    DeviceCredential.query.filter_by(device_id=device_id).delete()
    DeviceInterface.query.filter_by(device_id=device_id).delete()
    DeviceConfigBackup.query.filter_by(device_id=device_id).delete()
    DeviceCollectTask.query.filter_by(device_id=device_id).delete()
    # 置空可空外键引用，避免悬挂外键（SQLite 默认不强制 FK）
    Ticket.query.filter_by(related_device_id=device_id).update({'related_device_id': None})
    RackInstall.query.filter_by(device_id=device_id).update({'device_id': None})
    cid = d.customer_id
    db.session.delete(d)
    return cid


# 保留旧式（customer_name 字符串）
@transaction
def create_device(data):
    """旧式新增：通过 customer_name 字符串查找客户（保留兼容）"""
    name = (data.get('device_name') or '').strip()
    if not name:
        raise ServiceError('设备名称不能为空')
    if Device.query.filter_by(device_name=name).first():
        raise ServiceError(f'设备 "{name}" 已存在')

    customer = None
    cust_name = (data.get('customer_name') or '').strip()
    if cust_name:
        customer = Customer.query.filter_by(name=cust_name).first()
        if not customer:
            raise ServiceError(f'客户 "{cust_name}" 不存在')

    plain_password = data.get('password', '')
    encrypted = encrypt_password(plain_password) if plain_password else ''

    d = Device(
        customer_id=customer.id if customer else None,
        device_name=name,
        device_type=data.get('device_type', ''),
        brand=data.get('brand', ''),
        model=data.get('model', ''),
        serial_number=data.get('serial_number', ''),
        ip_address=data.get('ip_address', ''),
        port=int(data.get('port') or 22),
        username=data.get('username', ''),
        password_encrypted=encrypted,
        login_method=data.get('login_method', ''),
        os_version=data.get('os_version', ''),
        rule_version=data.get('rule_version', ''),
        is_maintenance=_to_bool(data.get('is_maintenance')),
        is_in_use=_to_bool(data.get('is_in_use')),
        license_expiry=_parse_date(data.get('license_expiry')),
        remark=data.get('remark', ''),
    )
    db.session.add(d)
    return d


def get_low_stock_parts():
    """查询库存低于下限的备件（单次聚合）"""
    from sqlalchemy import func
    rows = db.session.query(
        SparePart.id, SparePart.min_stock, SparePart.name,
        func.coalesce(func.sum(SpareStock.quantity), 0)
    ).outerjoin(SpareStock, SpareStock.spare_part_id == SparePart.id
    ).group_by(SparePart.id).all()
    return [(pid, name, qty) for pid, min_s, name, qty in rows
            if (min_s or 0) > 0 and qty < min_s]


# ============================ 内部工具 ============================
def _to_bool(val):
    if isinstance(val, bool):
        return val
    return str(val).strip().lower() in ('是', '1', 'true', 'on', 'yes', 'y')


def _parse_date(s):
    if not s:
        return None
    try:
        return datetime.strptime(s.strip(), '%Y-%m-%d').date()
    except (ValueError, TypeError):
        return None

