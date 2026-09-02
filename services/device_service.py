# -*- coding: utf-8 -*-
"""Device 业务服务

支持两种调用风格：
- create_device_from_form(form_dict): web 路由用（接收 customer_id 整数）
- create_device(data): 旧式（接收 customer_name 字符串，内部查找）
"""
import re
from datetime import date, datetime
from models import db, Device, Customer, SparePart, SpareStock, DevicePowerConfig
from utils.crypto import encrypt_password
from utils.json_fields import dumps_json
from utils.constants import (DEVICE_INSTALLATION_POSITIONS, DEVICE_POWER_SUPPLIES,
                             DEVICE_LOGIN_METHODS)
from .base import ServiceError, transaction


# 简单的 IPv4 校验（仅用于提示，不强制）
IPV4_RE = re.compile(r'^(\d{1,3}\.){3}\d{1,3}$')

DEVICE_CHOICE_FIELDS = {
    'location': ('安装位置', DEVICE_INSTALLATION_POSITIONS),
    'login_method': ('登录方式', DEVICE_LOGIN_METHODS),
}


def get_power_supply_choices():
    """从字典读取当前可用电源配置；新建库未种子时回退内置值。"""
    try:
        values = [item.name for item in DevicePowerConfig.query.filter_by(is_active=True).order_by(
            DevicePowerConfig.sort_order, DevicePowerConfig.id).all()]
    except Exception:
        values = []
    return tuple(values) or DEVICE_POWER_SUPPLIES


def normalize_device_choice(field, value, current_value=None):
    """规范设备枚举字段；更新时允许原样保留尚未清洗的历史值。"""
    text = str(value or '').strip()
    if field == 'power_supply':
        label, choices = '电源配置', get_power_supply_choices()
    else:
        label, choices = DEVICE_CHOICE_FIELDS[field]
    if text and text not in choices:
        if current_value is not None and text == str(current_value or '').strip():
            return text
        raise ServiceError(f'{label}仅支持：{"、".join(choices)}')
    return text


def normalize_rated_power(value):
    """额定功率以整机输入瓦数保存；空值表示未核实。"""
    if value in (None, ''):
        return None
    if isinstance(value, bool):
        raise ServiceError('额定功率必须为非负整数（W）')
    text = str(value).strip()
    try:
        number = float(text)
    except (TypeError, ValueError) as exc:
        raise ServiceError('额定功率必须为非负整数（W）') from exc
    if not number.is_integer() or number < 0 or number > 10_000_000:
        raise ServiceError('额定功率必须为 0-10000000 之间的整数（W）')
    return int(number)


def _rack_side(value):
    side = str(value or '').strip()
    return side if side in {'正面', '背面'} else ''


def _rack_install_side(install):
    if install.install_side:
        return _rack_side(install.install_side)
    return _rack_side(install.device_rel.location if install.device_rel else '')


def _rack_sides_conflict(left, right):
    left_side, right_side = _rack_side(left), _rack_side(right)
    return not (left_side and right_side and left_side != right_side)


def _sync_rack_placement(device, form):
    """按设备表单同步机柜位置；与设备字段共用当前事务。

    ``rack_id`` 是显式开关：旧表单没有该字段时保持原上架关系不动；Vue 表单
    传空值表示下架，传机柜 ID 表示上架或迁柜。未上架设备的机房位置保存在
    devices.rack_location，已上架设备的机房位置由 Rack.location 单一派生。
    """
    data = form.to_dict() if hasattr(form, 'to_dict') else form
    custom_name = str(data.get('rack_custom_name') or '').strip()[:64]
    if 'rack_id' not in data and not custom_name:
        if 'rack_location' in data and not device.rack_installs:
            device.rack_location = str(data.get('rack_location') or '').strip()[:128]
        return

    from models import Rack, RackInstall

    installs = (RackInstall.query.filter_by(device_id=device.id)
                .order_by(RackInstall.id.desc()).all())
    current = installs[0] if installs else None
    rack_id = data.get('rack_id')
    if custom_name:
        if not device.customer_id:
            raise ServiceError('自定义机柜前必须选择客户')
        rack_location = str(data.get('rack_location') or '').strip()[:128]
        rack = Rack.query.filter_by(
            customer_id=device.customer_id,
            name=custom_name,
            location=rack_location,
        ).order_by(Rack.id).first()
        if not rack:
            rack = Rack(
                customer_id=device.customer_id,
                name=custom_name,
                location=rack_location,
                total_u=42,
            )
            db.session.add(rack)
            db.session.flush()
        rack_id = rack.id
    if rack_id in (None, ''):
        for install in installs:
            db.session.delete(install)
        device.rack_location = str(data.get('rack_location') or '').strip()[:128]
        return

    try:
        rack_id = int(rack_id)
    except (TypeError, ValueError) as exc:
        raise ServiceError('机柜参数无效') from exc
    rack = Rack.query.get(rack_id)
    if not rack:
        raise ServiceError('所选机柜不存在')
    if rack.customer_id != device.customer_id:
        raise ServiceError('设备与机柜必须属于同一客户')

    default_start = current.start_u if current and current.rack_id == rack.id else 1
    default_occupy = current.occupy_u if current else 1
    install_side = _rack_side(data.get('rack_install_side') or device.location)
    try:
        start_u = int(data.get('rack_start_u') or default_start)
        occupy_u = int(data.get('rack_occupy_u') or default_occupy)
    except (TypeError, ValueError) as exc:
        raise ServiceError('机柜 U 位参数无效') from exc
    if start_u < 1 or occupy_u < 1:
        raise ServiceError('机柜 U 位和占用 U 数必须大于 0')
    if start_u + occupy_u - 1 > (rack.total_u or 0):
        raise ServiceError(f'U 位超出范围（机柜共 {rack.total_u or 0}U）')

    own_install_ids = {install.id for install in installs}
    new_end = start_u + occupy_u - 1
    for other in rack.installs:
        if other.id in own_install_ids:
            continue
        other_start = other.start_u or 1
        other_end = other_start + (other.occupy_u or 1) - 1
        if (not (new_end < other_start or start_u > other_end)
                and _rack_sides_conflict(install_side, _rack_install_side(other))):
            raise ServiceError(f'U 位冲突：{other_start}U-{other_end}U 已被占用')

    if current:
        current.rack_id = rack.id
        current.rack_rel = rack
        current.start_u = start_u
        current.occupy_u = occupy_u
        current.install_side = install_side
    else:
        current = RackInstall(
            rack_id=rack.id, device_id=device.id,
            start_u=start_u, occupy_u=occupy_u, install_side=install_side,
        )
        db.session.add(current)
    for stale in installs[1:]:
        db.session.delete(stale)
    device.rack_location = ''


@transaction
def create_device_from_form(form):
    """新增设备（接收 web 表单 form 字典）

    表单字段：device_name/customer_id/region_id/device_type/brand/model/
              ip_address/port/username/password/serial_number/login_method/
              location/power_supply/interface(多值)/os_version/rule_version/is_maintenance/
              is_in_use/license_expiry/remark
    """
    name = (form.get('device_name') or '').strip()
    if not name:
        raise ServiceError('设备名称不能为空')

    customer_id = form.get('customer_id')
    if customer_id:
        try:
            customer_id = int(customer_id)
        except (TypeError, ValueError):
            customer_id = None
    else:
        customer_id = None
    if Device.query.filter_by(customer_id=customer_id, device_name=name).first():
        raise ServiceError(f'当前客户下设备 "{name}" 已存在')

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
        login_method=normalize_device_choice('login_method', form.get('login_method')),
        location=normalize_device_choice('location', form.get('location')),
        rack_location=str(form.get('rack_location') or '').strip()[:128],
        interface=dumps_json(interfaces) if interfaces else None,
        power_supply=normalize_device_choice('power_supply', form.get('power_supply')),
        rated_power_w=normalize_rated_power(form.get('rated_power_w')),
        os_version=form.get('os_version', ''),
        rule_version=form.get('rule_version', ''),
        network_type=form.get('network_type', ''),
        is_maintenance=form.get('is_maintenance') == 'on',
        is_in_use=form.get('is_in_use') == 'on',
        license_expiry=_parse_date(form.get('license_expiry')),
        license_start=_parse_date(form.get('license_start')),
        build_date=_parse_date(form.get('build_date')),
        cert_expiry_date=_parse_date(form.get('cert_expiry_date')),
        remark=form.get('remark', ''),
    )
    db.session.add(d)
    db.session.flush()
    _sync_rack_placement(d, form)
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

    # 历史数据中同一客户可能存在真实的同名设备。仅修改密码、
    # 品牌等非身份字段时，不能因为另一条历史同名记录而拒绝更新。
    # 只在所属客户或设备名称真正变更时阻止制造新的同名冲突。
    identity_changed = customer_id != d.customer_id or name != d.device_name
    if identity_changed:
        duplicate = Device.query.filter_by(
            customer_id=customer_id, device_name=name,
        ).filter(Device.id != d.id).first()
        if duplicate:
            raise ServiceError(f'当前客户下设备 "{name}" 已存在')

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
    d.login_method = normalize_device_choice('login_method', form.get('login_method'), d.login_method)
    d.location = normalize_device_choice('location', form.get('location'), d.location)
    interfaces = [v.strip() for v in form.getlist('interface') if v.strip()] if hasattr(form, 'getlist') else []
    d.interface = dumps_json(interfaces) if interfaces else None
    d.power_supply = normalize_device_choice('power_supply', form.get('power_supply'))
    d.rated_power_w = normalize_rated_power(form.get('rated_power_w'))
    d.os_version = form.get('os_version', '')
    d.rule_version = form.get('rule_version', '')
    d.network_type = form.get('network_type', '')
    d.is_maintenance = form.get('is_maintenance') == 'on'
    d.is_in_use = form.get('is_in_use') == 'on'
    d.license_expiry = _parse_date(form.get('license_expiry'))
    d.license_start = _parse_date(form.get('license_start'))
    d.build_date = _parse_date(form.get('build_date'))
    d.cert_expiry_date = _parse_date(form.get('cert_expiry_date'))
    d.remark = form.get('remark', '')
    _sync_rack_placement(d, form)
    return d


@transaction
def delete_device(device_id):
    """删除设备（清理关联的密码历史、凭据、接口、配置备份、采集任务；置空工单/上架的设备引用）"""
    d = Device.query.get_or_404(device_id)
    return _delete_device_no_commit(d)


def _delete_device_no_commit(d):
    """单设备删除内核，不提交，供单删与批量删除共用。"""
    device_id = d.id
    from models import (PasswordHistory, DeviceCredential, DeviceInterface,
                        DeviceConfigBackup, DeviceCollectTask, Ticket, RackInstall,
                        InspectionTask)
    from utils.json_fields import parse_json, dumps_json
    PasswordHistory.query.filter_by(device_id=device_id).delete()
    DeviceCredential.query.filter_by(device_id=device_id).delete()
    DeviceInterface.query.filter_by(device_id=device_id).delete()
    DeviceConfigBackup.query.filter_by(device_id=device_id).delete()
    DeviceCollectTask.query.filter_by(device_id=device_id).delete()
    # 置空可空外键引用，避免悬挂外键（SQLite 默认不强制 FK）
    Ticket.query.filter_by(related_device_id=device_id).update({'related_device_id': None})
    # 上架记录：快照设备信息，机柜仍保留占位（避免渲染为"(未命名)"）
    for ri in RackInstall.query.filter_by(device_id=device_id).all():
        ri.device_id = None
        ri.manual_name = d.device_name
        ri.manual_brand = d.brand or ''
        ri.manual_model = d.model or ''
        ri.manual_ip = d.ip_address or ''
        ri.install_side = _rack_side(d.location)
        ri.rated_w = d.rated_power_w
    # 巡检任务 device_ids_json 剔除该设备 id
    for t in InspectionTask.query.filter(InspectionTask.device_ids_json.isnot(None)).all():
        try:
            ids = [x for x in parse_json(t.device_ids_json, [], 'task.device_ids_json')
                   if isinstance(x, int) and x != device_id]
        except (TypeError, ValueError):
            continue
        t.device_ids_json = dumps_json(ids)
    cid = d.customer_id
    db.session.delete(d)
    return cid


def preview_device_delete(devices):
    """返回批量删除会处理的依赖摘要（不改数据）。"""
    from models import DeviceConfigBackup, Ticket, RackInstall, InspectionTask
    from utils.json_fields import parse_json
    ids = {device.id for device in devices}
    inspection_tasks = 0
    for task in InspectionTask.query.filter(InspectionTask.device_ids_json.isnot(None)).all():
        values = parse_json(task.device_ids_json, [], 'task.device_ids_json')
        if isinstance(values, list) and ids.intersection(
                int(value) for value in values if str(value).isdigit()):
            inspection_tasks += 1
    return {
        'count': len(devices),
        'tickets': Ticket.query.filter(Ticket.related_device_id.in_(ids)).count(),
        'inspection_tasks': inspection_tasks,
        'config_backups': DeviceConfigBackup.query.filter(
            DeviceConfigBackup.device_id.in_(ids)).count(),
        'rack_installs': RackInstall.query.filter(RackInstall.device_id.in_(ids)).count(),
        'names': [device.device_name for device in devices],
    }


@transaction
def delete_devices(devices):
    """批次全部成功或全部回滚，与单设备删除共用同一内核。"""
    customer_ids = set()
    for device in devices:
        customer_id = _delete_device_no_commit(device)
        if customer_id:
            customer_ids.add(customer_id)
    return customer_ids


def sync_customer_device_count(customer_id):
    """刷新客户 device_count 冗余字段与自动定级（统一入口，全量口径）。

    口径 = devices 表实际行数（含停用/不在用设备），与删除客户时的
    c.devices.count() 拦截校验一致，避免「UI 设备数」与删除校验矛盾。
    内部 commit，幂等可重复调用；返回最新设备数。
    """
    if not customer_id:
        return 0
    from services.customer_service import _calculate_tier
    cnt = Device.query.filter_by(customer_id=customer_id).count()
    c = Customer.query.get(customer_id)
    if c:
        c.device_count = cnt
        if not c.level or c.level not in ('核心', '重点', '常规'):
            c.level = _calculate_tier(cnt, bool(c.has_onsite), bool(c.has_drill))
        db.session.commit()
    return cnt


# 保留旧式（customer_name 字符串）
@transaction
def create_device(data):
    """旧式新增：通过 customer_name 字符串查找客户（保留兼容）"""
    name = (data.get('device_name') or '').strip()
    if not name:
        raise ServiceError('设备名称不能为空')

    customer = None
    cust_name = (data.get('customer_name') or '').strip()
    if cust_name:
        customer = Customer.query.filter_by(name=cust_name).first()
        if not customer:
            raise ServiceError(f'客户 "{cust_name}" 不存在')
    if Device.query.filter_by(
            customer_id=customer.id if customer else None, device_name=name).first():
        raise ServiceError(f'当前客户下设备 "{name}" 已存在')

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
        login_method=normalize_device_choice('login_method', data.get('login_method')),
        location=normalize_device_choice('location', data.get('location')),
        power_supply=normalize_device_choice('power_supply', data.get('power_supply')),
        rated_power_w=normalize_rated_power(data.get('rated_power_w')),
        os_version=data.get('os_version', ''),
        rule_version=data.get('rule_version', ''),
        is_maintenance=_to_bool(data.get('is_maintenance')),
        is_in_use=_to_bool(data.get('is_in_use')),
        license_expiry=_parse_date(data.get('license_expiry')),
        license_start=_parse_date(data.get('license_start')),
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
    if isinstance(s, datetime):
        return s.date()
    if isinstance(s, date):
        return s
    text = str(s).strip()
    for fmt in ('%Y-%m-%d', '%Y/%m/%d', '%Y.%m.%d', '%Y-%m-%d %H:%M:%S'):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None
