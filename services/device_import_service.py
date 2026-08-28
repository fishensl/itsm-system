# -*- coding: utf-8 -*-
"""设备 Excel 导入的预检与执行服务。

路由只负责解析工作簿；匹配、字段校验、空值语义和位置处理在此统一。
"""
import re

from models import db, Device, PasswordHistory, Rack, RackInstall
from services.base import ServiceError
from services.device_service import (
    _parse_date,
    _sync_rack_placement,
    normalize_device_choice,
    normalize_rated_power,
)
from utils.crypto import encrypt_password
from utils.json_fields import dumps_json

IMPORT_MODES = {'create', 'update', 'upsert'}
TEXT_FIELDS = (
    'device_type', 'brand', 'model', 'serial_number', 'network_type', 'ip_address',
    'username', 'os_version', 'rule_version', 'rack_location', 'remark',
)
DATE_FIELDS = ('build_date', 'license_start', 'license_expiry', 'cert_expiry_date')
BOOL_FIELDS = ('is_maintenance', 'is_in_use')


def _truthy(value):
    return str(value or '').strip().lower() in {'是', '1', 'true', 'on', 'yes', 'y'}


def _present(row, field, clear_empty=False):
    return field in row.get('_present', set()) and (clear_empty or row.get(field) not in ('', None))


def _resolve_match(row, customer, accessible_device_ids):
    raw_id = str(row.get('device_id') or '').strip()
    if raw_id:
        try:
            device_id = int(float(raw_id))
        except (TypeError, ValueError) as exc:
            raise ServiceError('设备ID必须为整数') from exc
        device = db.session.get(Device, device_id)
        if not device or device.id not in accessible_device_ids:
            raise ServiceError(f'设备ID {device_id} 不存在或不在当前数据范围')
        if customer and device.customer_id != customer.id:
            raise ServiceError('设备ID与客户不匹配')
        return device
    if not customer:
        return None
    matches = Device.query.filter_by(
        customer_id=customer.id, device_name=str(row.get('device_name') or '').strip(),
    ).all()
    visible = [item for item in matches if item.id in accessible_device_ids]
    if len(visible) > 1:
        raise ServiceError('同一客户存在多条同名设备，请先清理重复数据或填写设备ID')
    return visible[0] if visible else None


def _normalized_values(row, existing=None, clear_empty=False):
    values = {}
    for field in TEXT_FIELDS:
        if _present(row, field, clear_empty):
            values[field] = str(row.get(field) or '').strip()
    if _present(row, 'port', clear_empty):
        raw_port = row.get('port')
        if raw_port in ('', None) and clear_empty:
            values['port'] = 22
        else:
            try:
                port = int(float(str(raw_port)))
            except (TypeError, ValueError) as exc:
                raise ServiceError('端口必须为整数') from exc
            if port < 1 or port > 65535:
                raise ServiceError('端口必须为 1-65535')
            values['port'] = port
    if _present(row, 'location', clear_empty):
        values['location'] = normalize_device_choice(
            'location', row.get('location'), existing.location if existing else None)
    if _present(row, 'power_supply', clear_empty):
        values['power_supply'] = normalize_device_choice(
            'power_supply', row.get('power_supply'), existing.power_supply if existing else None)
    if _present(row, 'login_method', clear_empty):
        values['login_method'] = normalize_device_choice(
            'login_method', row.get('login_method'), existing.login_method if existing else None)
    if _present(row, 'rated_power_w', clear_empty):
        values['rated_power_w'] = normalize_rated_power(row.get('rated_power_w'))
    if _present(row, 'interface', clear_empty):
        interfaces = [item.strip() for item in re.split(
            r'[、,，;；\n]+', str(row.get('interface') or '')) if item.strip()]
        values['interface'] = dumps_json(interfaces) if interfaces else None
    for field in DATE_FIELDS:
        if _present(row, field, clear_empty):
            values[field] = _parse_date(row.get(field))
    for field in BOOL_FIELDS:
        if _present(row, field, clear_empty):
            values[field] = _truthy(row.get(field))
    password = str(row.get('password') or '') if _present(row, 'password') else ''
    return values, password


def _normalize_rack_slot(row):
    """兼容列表/旧资产表的聚合 U 位，如 ``27U-30U`` 或 ``5U``。

    新模板仍使用独立的“起始U位、占用U数”；聚合值只在导出回灌时拆分，
    并与显式占用数交叉校验，防止两个值互相矛盾。
    """
    if not _present(row, 'rack_start_u'):
        return
    text = str(row.get('rack_start_u') or '').strip()
    if not text:
        return
    match = re.fullmatch(
        r'(\d+)\s*[uU]?(?:\s*(?:-|~|～|至|—|–)\s*(\d+)\s*[uU]?)?', text)
    if not match:
        return
    start_u = int(match.group(1))
    range_end = match.group(2)
    end_u = int(range_end or start_u)
    if end_u < start_u:
        raise ServiceError('起始U位范围的结束值不能小于开始值')
    explicit_occupy = str(row.get('rack_occupy_u') or '').strip()
    if range_end and explicit_occupy:
        derived_occupy = end_u - start_u + 1
        try:
            explicit_number = float(explicit_occupy)
        except (TypeError, ValueError) as exc:
            raise ServiceError('占用U数必须为整数') from exc
        if not explicit_number.is_integer() or int(explicit_number) != derived_occupy:
            raise ServiceError(
                f'聚合 U 位表示占用 {derived_occupy}U，与“占用U数”不一致')
    row['rack_start_u'] = str(start_u)
    # 只有聚合范围或缺少独立“占用U数”时才反推；普通起始值不能把显式占用数覆盖为 1。
    if range_end or not explicit_occupy:
        row['rack_occupy_u'] = str(end_u - start_u + 1)
        row.setdefault('_present', set()).add('rack_occupy_u')


def _validate_rack_placement(row, customer, existing, clear_empty, planned_slots):
    """只读校验客户/机柜/U 位组合，并记录本批次内的占用区间。"""
    location_fields = {'rack_location', 'rack_name', 'rack_start_u', 'rack_occupy_u'}
    if not any(_present(row, field, clear_empty) for field in location_fields):
        return False
    rack_name = str(row.get('rack_name') or '').strip()
    if not rack_name:
        if _present(row, 'rack_start_u') or _present(row, 'rack_occupy_u'):
            raise ServiceError('填写 U 位时必须同时填写机柜号')
        # 明确允许空值清除时，空机柜号表示下架；否则仅更新未上架设备自身机房位置。
        return True
    if not customer:
        raise ServiceError('填写机柜号前必须选择客户')
    rack_location = str(row.get('rack_location') or '').strip()[:128]
    rack = Rack.query.filter_by(
        customer_id=customer.id, name=rack_name, location=rack_location,
    ).order_by(Rack.id).first()
    total_u = rack.total_u if rack else 42
    try:
        raw_start = float(str(row.get('rack_start_u') or 1))
        raw_occupy = float(str(row.get('rack_occupy_u') or 1))
    except (TypeError, ValueError) as exc:
        raise ServiceError('机柜 U 位参数必须为整数') from exc
    if not raw_start.is_integer() or not raw_occupy.is_integer():
        raise ServiceError('机柜 U 位参数必须为整数')
    start_u, occupy_u = int(raw_start), int(raw_occupy)
    if start_u < 1 or occupy_u < 1:
        raise ServiceError('机柜 U 位和占用 U 数必须大于 0')
    end_u = start_u + occupy_u - 1
    if end_u > total_u:
        raise ServiceError(f'U 位超出范围（机柜共 {total_u}U）')

    own_install_ids = {
        item.id for item in RackInstall.query.filter_by(device_id=existing.id).all()
    } if existing else set()
    if rack:
        for other in rack.installs:
            if other.id in own_install_ids:
                continue
            other_start = other.start_u or 1
            other_end = other_start + (other.occupy_u or 1) - 1
            if not (end_u < other_start or start_u > other_end):
                raise ServiceError(f'U 位冲突：{other_start}U-{other_end}U 已被占用')
    rack_key = (customer.id, rack_name, rack_location)
    for other_row, other_start, other_end in planned_slots.get(rack_key, []):
        if not (end_u < other_start or start_u > other_end):
            raise ServiceError(
                f'与本次导入第{other_row}行 U 位冲突：{other_start}U-{other_end}U')
    planned_slots.setdefault(rack_key, []).append((row['_row'], start_u, end_u))
    return True


def prepare_device_import(rows, customers, accessible_device_ids, allow_unassigned,
                          mode='create', network_mappings=None, clear_empty=False):
    """返回可执行计划和预检摘要，未知网络类型按值聚合行号。"""
    if mode not in IMPORT_MODES:
        raise ServiceError('导入模式无效')
    network_mappings = {str(k).strip(): str(v).strip()
                        for k, v in (network_mappings or {}).items() if str(k).strip()}
    from models import NetworkType
    valid_networks = {item.name for item in NetworkType.query.all()}
    bad_mappings = {source: target for source, target in network_mappings.items()
                    if target not in valid_networks}
    if bad_mappings:
        raise ServiceError('网络类型映射目标不存在：' + '、'.join(bad_mappings.values()))

    plan = []
    errors = []
    error_details = []
    unknown = {}
    seen_targets = {}
    planned_slots = {}
    counts = {'create': 0, 'update': 0, 'unchanged': 0, 'skipped': 0, 'failed': 0}
    for row in rows:
        row_no = row['_row']
        name = str(row.get('device_name') or '').strip()
        if not name:
            message = f'第{row_no}行：设备名称为空'
            errors.append(message)
            error_details.append((row_no, name, message))
            counts['failed'] += 1
            continue
        customer_name = str(row.get('customer_name') or '').strip()
        customer = customers.get(customer_name) if customer_name else None
        if customer_name and not customer:
            message = f'第{row_no}行：客户「{customer_name}」不存在或不在当前数据范围'
            errors.append(message)
            error_details.append((row_no, name, message))
            counts['failed'] += 1
            continue
        if not customer and not allow_unassigned:
            message = f'第{row_no}行：受限用户必须填写可见客户'
            errors.append(message)
            error_details.append((row_no, name, message))
            counts['failed'] += 1
            continue
        raw_device_id = str(row.get('device_id') or '').strip()
        target_key = ('id', raw_device_id) if raw_device_id else (
            'name', customer.id if customer else None, name)
        if target_key in seen_targets:
            message = (f'第{row_no}行（{name}）：与第{seen_targets[target_key]}行指向同一设备，'
                       '请合并为一行')
            errors.append(message)
            error_details.append((row_no, name, message))
            counts['failed'] += 1
            continue
        seen_targets[target_key] = row_no
        network = str(row.get('network_type') or '').strip()
        if network and network not in valid_networks:
            mapped = network_mappings.get(network)
            if mapped:
                row['network_type'] = mapped
            else:
                unknown.setdefault(network, []).append(row_no)
                continue
        try:
            existing = _resolve_match(row, customer, accessible_device_ids)
            if not customer and existing is None and str(row.get('device_id') or '').strip():
                raise ServiceError('未找到可更新的设备')
            if not customer and existing is None and mode != 'create':
                raise ServiceError('未归属客户的设备更新必须填写设备ID')
            _normalize_rack_slot(row)
            values, password = _normalized_values(row, existing, clear_empty)
            if existing:
                if mode == 'create':
                    counts['skipped'] += 1
                    plan.append({'action': 'skip', 'row': row, 'device': existing})
                    continue
                location_changed = _validate_rack_placement(
                    row, customer, existing, clear_empty, planned_slots)
                changed = (any(getattr(existing, key) != value for key, value in values.items()) or
                           bool(password) or location_changed)
                action = 'update' if changed else 'unchanged'
            else:
                if mode == 'update':
                    counts['skipped'] += 1
                    plan.append({'action': 'skip', 'row': row, 'device': None})
                    continue
                _validate_rack_placement(
                    row, customer, existing, clear_empty, planned_slots)
                action = 'create'
            counts[action] += 1
            plan.append({'action': action, 'row': row, 'device': existing,
                         'customer': customer, 'values': values, 'password': password})
        except Exception as exc:  # noqa: BLE001
            message = f'第{row_no}行（{name}）：{exc}'
            errors.append(message)
            error_details.append((row_no, name, message))
            counts['failed'] += 1

    for value, row_numbers in unknown.items():
        shown = '、'.join(str(number) for number in row_numbers[:30])
        suffix = '…' if len(row_numbers) > 30 else ''
        errors.append(f'未知网络类型「{value}」：第 {shown}{suffix} 行')
        for row_no in row_numbers:
            row_name = next((str(row.get('device_name') or '') for row in rows
                             if row.get('_row') == row_no), '')
            error_details.append((row_no, row_name, f'网络类型「{value}」不在系统设置中'))
        counts['failed'] += len(row_numbers)
    return {'plan': plan, 'counts': counts, 'errors': errors,
            'error_details': error_details, 'unknown_network_types': unknown,
            'network_type_options': sorted(valid_networks), 'clear_empty': clear_empty}


def execute_device_import(prepared, operator_name=''):
    """在调用方事务中执行已预检的计划。"""
    password_updates = 0
    affected_customers = set()
    for item in prepared['plan']:
        if item['action'] not in {'create', 'update'}:
            continue
        row = item['row']
        if item['action'] == 'create':
            device = Device(
                customer_id=item['customer'].id if item.get('customer') else None,
                device_name=str(row.get('device_name') or '').strip(),
                port=22,
                is_in_use=True,
            )
            db.session.add(device)
            db.session.flush()
        else:
            device = item['device']
        for key, value in item['values'].items():
            setattr(device, key, value)
        if item['password']:
            if item['action'] == 'update' and device.password_encrypted:
                db.session.add(PasswordHistory(
                    device_id=device.id, password_encrypted=device.password_encrypted,
                    changed_by=operator_name, remark='Excel 批量导入更新',
                ))
            device.password_encrypted = encrypt_password(item['password'])
            password_updates += 1
        location_fields = {'rack_location', 'rack_name', 'rack_start_u', 'rack_occupy_u'}
        clear_empty = bool(prepared.get('clear_empty'))
        if any(_present(row, field, clear_empty) for field in location_fields):
            placement = {
                'rack_location': row.get('rack_location', ''),
                'rack_custom_name': row.get('rack_name', ''),
                'rack_start_u': row.get('rack_start_u') or 1,
                'rack_occupy_u': row.get('rack_occupy_u') or 1,
            }
            if clear_empty and 'rack_name' in row.get('_present', set()) and not row.get('rack_name'):
                placement['rack_id'] = None
            _sync_rack_placement(device, placement)
        if device.customer_id:
            affected_customers.add(device.customer_id)
    return {'password_updates': password_updates, 'customer_ids': affected_customers}
