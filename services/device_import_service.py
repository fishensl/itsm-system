# -*- coding: utf-8 -*-
"""设备 Excel 导入的预检与执行服务。

路由只负责解析工作簿；匹配、字段校验、空值语义和位置处理在此统一。
"""
import re
from datetime import date, datetime

from models import db, Device, PasswordHistory, Rack, RackInstall, Brand, DeviceType
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
DATE_FIELD_LABELS = {
    'build_date': '建设时间',
    'license_start': '授权开始日期',
    'license_expiry': '授权截止日期',
    'cert_expiry_date': '证书到期日期',
}
BOOL_FIELDS = ('is_maintenance', 'is_in_use')
INSTALL_SIDES = {'正面', '背面'}


def normalize_device_import_cell(field, value):
    """Normalize an Excel cell without leaking a synthetic midnight into text fields.

    Excel may store values such as a rule-library version as a date-formatted cell.
    openpyxl then returns ``datetime(YYYY, M, D, 0, 0)``. Lifecycle fields retain the
    native value for strict date parsing; ordinary device text fields keep only the
    calendar date instead of persisting ``00:00:00`` as part of the version string.
    """
    if value is None:
        return ''
    if field in DATE_FIELDS:
        return value
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return str(value).strip()


def _truthy(value):
    return str(value or '').strip().lower() in {'是', '1', 'true', 'on', 'yes', 'y'}


def _present(row, field, clear_empty=False):
    return field in row.get('_present', set()) and (clear_empty or row.get(field) not in ('', None))


def _identity_value(value):
    """Normalize identity fields without changing their stored/display value."""
    return str(value or '').strip().casefold()


def _rack_side(value):
    """Only known sides can make overlapping U ranges independent."""
    side = str(value or '').strip()
    return side if side in INSTALL_SIDES else ''


def _install_side(install):
    if install.install_side:
        return _rack_side(install.install_side)
    return _rack_side(install.device_rel.location if install.device_rel else '')


def _sides_conflict(left, right):
    """Unknown legacy side stays conservative; known opposite sides may overlap."""
    left_side, right_side = _rack_side(left), _rack_side(right)
    return not (left_side and right_side and left_side != right_side)


def _rack_identity_matches(row, candidates):
    """Return candidate ids matching the supplied rack number and start U."""
    rack_name = _identity_value(row.get('rack_name'))
    raw_start = str(row.get('rack_start_u') or '').strip()
    if not rack_name or not raw_start:
        return set()
    try:
        start_number = float(raw_start)
    except (TypeError, ValueError):
        return set()
    if not start_number.is_integer():
        return set()
    start_u = int(start_number)
    room = _identity_value(row.get('rack_location'))
    side = _rack_side(row.get('location'))
    candidate_ids = {item.id for item in candidates}
    installs = (RackInstall.query.join(Rack, Rack.id == RackInstall.rack_id)
                .filter(RackInstall.device_id.in_(candidate_ids))
                .order_by(RackInstall.id.desc()).all())
    latest = {}
    for install in installs:
        latest.setdefault(install.device_id, install)
    matched = set()
    for device_id, install in latest.items():
        rack = install.rack_rel
        if not rack or _identity_value(rack.name) != rack_name or install.start_u != start_u:
            continue
        if room and _identity_value(rack.location) != room:
            continue
        if side and _install_side(install) and _install_side(install) != side:
            continue
        matched.add(device_id)
    return matched


def _resolve_duplicate_name(row, candidates):
    """Resolve a legacy duplicate name only when supplied identity is unique."""
    unique_matches = []
    for field in ('serial_number', 'ip_address'):
        expected = _identity_value(row.get(field))
        if not expected:
            continue
        matched = {item.id for item in candidates
                   if _identity_value(getattr(item, field)) == expected}
        if len(matched) == 1:
            unique_matches.append((field, next(iter(matched))))
    rack_matches = _rack_identity_matches(row, candidates)
    if len(rack_matches) == 1:
        unique_matches.append(('rack', next(iter(rack_matches))))
    if not unique_matches:
        return None
    resolved_ids = {device_id for _field, device_id in unique_matches}
    if len(resolved_ids) != 1:
        raise ServiceError('序列号、IP 与机柜位置指向不同设备，请核对后再导入')
    resolved_id = next(iter(resolved_ids))
    return next(item for item in candidates if item.id == resolved_id)


def _resolve_match(row, customer, accessible_device_ids, mode='create',
                   allow_unique_name_match=False):
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
    candidates = [item for item in Device.query.filter_by(customer_id=customer.id).all()
                  if item.id in accessible_device_ids]
    resolved = _resolve_duplicate_name(row, candidates)
    if resolved:
        return resolved

    # 名称不是设备唯一标识。新增模式允许同客户存在多台同名设备；更新/覆盖仅在
    # 工作簿没有序列号、IP、机柜位置等标识时，兼容唯一同名的旧模板。
    if mode == 'create':
        return None
    has_identity = any(_identity_value(row.get(field))
                       for field in ('serial_number', 'ip_address', 'rack_name', 'rack_start_u'))
    name = str(row.get('device_name') or '').strip()
    visible = [item for item in candidates if item.device_name == name]
    if has_identity:
        # 兼容不含设备 ID、但确实只描述一台同名设备的资产表；同一工作簿内
        # 名称重复时绝不走此回退，以免把多台设备合并。
        if allow_unique_name_match and len(visible) == 1:
            return visible[0]
        return None
    if len(visible) > 1:
        raise ServiceError(
            f'同一客户有 {len(visible)} 台同名设备，无法确定更新目标；'
            '请填写设备ID，或保留可唯一定位的序列号、IP、机柜号和起始U位')
    return visible[0] if visible else None


def _normalized_values(row, existing=None, clear_empty=False):
    values = {}
    for field in TEXT_FIELDS:
        if _present(row, field, clear_empty):
            values[field] = str(row.get(field) or '').strip()
            if field in {'device_type', 'brand'} and len(values[field]) > 64:
                raise ServiceError('设备类型和品牌名称不能超过64个字符')
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
            raw_value = row.get(field)
            parsed = _parse_date(raw_value)
            if raw_value not in ('', None) and parsed is None:
                raise ServiceError(
                    f'{DATE_FIELD_LABELS[field]}格式无效，请使用 YYYY-MM-DD')
            values[field] = parsed
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


def _snapshot_matches_row(install, row, start_u, occupy_u, side):
    """Return whether a detached rack snapshot is the device represented by this row."""
    if install.device_id is not None:
        return False
    if install.start_u != start_u or (install.occupy_u or 1) != occupy_u:
        return False
    if _identity_value(install.manual_name) != _identity_value(row.get('device_name')):
        return False
    for snapshot_field, row_field in (
        ('manual_ip', 'ip_address'),
        ('manual_brand', 'brand'),
        ('manual_model', 'model'),
    ):
        snapshot_value = _identity_value(getattr(install, snapshot_field))
        row_value = _identity_value(row.get(row_field))
        if snapshot_value and row_value and snapshot_value != row_value:
            return False
    install_side = _install_side(install)
    return not (side and install_side and side != install_side)


def _collect_snapshot_side_hints(rows, customers, valid_networks, network_mappings):
    """Infer sides for legacy detached snapshots from exact rows in this workbook.

    Old snapshots have no side value. Looking at all import rows first prevents the
    back-side row from being rejected merely because the matching front-side row
    appears later in the workbook.
    """
    hints = {}
    for row in rows:
        name = str(row.get('device_name') or '').strip()
        customer = customers.get(str(row.get('customer_name') or '').strip())
        network = str(row.get('network_type') or '').strip()
        if not name or not customer or (network and network not in valid_networks
                                        and network not in network_mappings):
            continue
        try:
            _normalize_rack_slot(row)
            _normalized_values(row, None, False)
            rack_name = str(row.get('rack_name') or '').strip()
            if not rack_name:
                continue
            rack = Rack.query.filter_by(
                customer_id=customer.id,
                name=rack_name,
                location=str(row.get('rack_location') or '').strip()[:128],
            ).order_by(Rack.id).first()
            side = _rack_side(row.get('location'))
            if not rack or not side:
                continue
            start_number = float(str(row.get('rack_start_u') or 1))
            occupy_number = float(str(row.get('rack_occupy_u') or 1))
            if not start_number.is_integer() or not occupy_number.is_integer():
                continue
            matches = [
                install for install in rack.installs
                if _snapshot_matches_row(
                    install, row, int(start_number), int(occupy_number), side)
            ]
            if len(matches) != 1:
                continue
            install_id = matches[0].id
            if install_id in hints and hints[install_id] != side:
                hints[install_id] = ''
            else:
                hints[install_id] = side
        except (ServiceError, TypeError, ValueError):
            continue
    return hints


def _validate_rack_placement(row, customer, existing, clear_empty, planned_slots,
                             claimed_install_ids, snapshot_side_hints):
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
    side = _rack_side(row.get('location'))
    reclaim_id = None
    if rack:
        if existing is None:
            reclaim_candidates = [
                other for other in rack.installs
                if other.id not in claimed_install_ids
                and _snapshot_matches_row(other, row, start_u, occupy_u, side)
            ]
            if len(reclaim_candidates) > 1:
                raise ServiceError('机柜中存在多条匹配的历史快照，无法确定关联目标')
            if reclaim_candidates:
                reclaim_id = reclaim_candidates[0].id
                row['_reclaim_rack_install_id'] = reclaim_id
                claimed_install_ids.add(reclaim_id)
        for other in rack.installs:
            if (other.id in own_install_ids or other.id == reclaim_id
                    or other.id in claimed_install_ids):
                continue
            other_start = other.start_u or 1
            other_end = other_start + (other.occupy_u or 1) - 1
            if (not (end_u < other_start or start_u > other_end)
                    and _sides_conflict(
                        side, snapshot_side_hints.get(other.id) or _install_side(other))):
                raise ServiceError(f'U 位冲突：{other_start}U-{other_end}U 已被占用')
    rack_key = (customer.id, rack_name, rack_location)
    for other_row, other_start, other_end, other_side in planned_slots.get(rack_key, []):
        if (not (end_u < other_start or start_u > other_end)
                and _sides_conflict(side, other_side)):
            raise ServiceError(
                f'与本次导入第{other_row}行 U 位冲突：{other_start}U-{other_end}U')
    planned_slots.setdefault(rack_key, []).append((row['_row'], start_u, end_u, side))
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
    claimed_install_ids = set()
    snapshot_side_hints = _collect_snapshot_side_hints(
        rows, customers, valid_networks, network_mappings)
    name_occurrences = {}
    for import_row in rows:
        name_key = (
            _identity_value(import_row.get('customer_name')),
            _identity_value(import_row.get('device_name')),
        )
        name_occurrences[name_key] = name_occurrences.get(name_key, 0) + 1
    counts = {'create': 0, 'update': 0, 'unchanged': 0, 'skipped': 0, 'failed': 0}
    known_dicts = {
        'device_type': {name for (name,) in db.session.query(DeviceType.name).all()},
        'brand': {name for (name,) in db.session.query(Brand.name).all()},
    }
    skip_details = []
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
        network = str(row.get('network_type') or '').strip()
        if network and network not in valid_networks:
            mapped = network_mappings.get(network)
            if mapped:
                row['network_type'] = mapped
            else:
                unknown.setdefault(network, []).append(row_no)
                continue
        claimed_before = set(claimed_install_ids)
        try:
            _normalize_rack_slot(row)
            name_key = (_identity_value(customer_name), _identity_value(name))
            existing = _resolve_match(
                row, customer, accessible_device_ids, mode,
                allow_unique_name_match=name_occurrences.get(name_key) == 1)
            if not customer and existing is None and str(row.get('device_id') or '').strip():
                raise ServiceError('未找到可更新的设备')
            if not customer and existing is None and mode != 'create':
                raise ServiceError('未归属客户的设备更新必须填写设备ID')
            if existing and mode == 'create':
                counts['skipped'] += 1
                skip_details.append({
                    'row': row_no,
                    'device_name': name,
                    'reason': '仅新增模式：系统中已存在匹配的正式设备',
                })
                plan.append({'action': 'skip', 'row': row, 'device': existing})
                continue
            if existing:
                target_key = ('id', existing.id)
            elif mode == 'update':
                counts['skipped'] += 1
                skip_details.append({
                    'row': row_no,
                    'device_name': name,
                    'reason': (
                        '仅更新模式：系统中不存在可更新的正式设备；'
                        '机柜手工记录不等于设备资产，请改用“仅新增”或“新增并更新”'
                    ),
                })
                plan.append({'action': 'skip', 'row': row, 'device': None})
                continue
            else:
                target_key = None
            if target_key is not None and target_key in seen_targets:
                raise ServiceError(
                    f'与第{seen_targets[target_key]}行指向同一设备，请合并为一行')
            if target_key is not None:
                seen_targets[target_key] = row_no
            values, password = _normalized_values(row, existing, clear_empty)
            if existing:
                location_changed = _validate_rack_placement(
                    row, customer, existing, clear_empty, planned_slots,
                    claimed_install_ids, snapshot_side_hints)
                changed = (any(getattr(existing, key) != value for key, value in values.items()) or
                           bool(password) or location_changed or
                           any(values.get(field) and values[field] not in names
                               for field, names in known_dicts.items()))
                action = 'update' if changed else 'unchanged'
            else:
                _validate_rack_placement(
                    row, customer, existing, clear_empty, planned_slots,
                    claimed_install_ids, snapshot_side_hints)
                action = 'create'
            counts[action] += 1
            plan.append({'action': action, 'row': row, 'device': existing,
                         'customer': customer, 'values': values, 'password': password})
        except Exception as exc:  # noqa: BLE001
            claimed_install_ids.clear()
            claimed_install_ids.update(claimed_before)
            row.pop('_reclaim_rack_install_id', None)
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
            'error_details': error_details, 'skip_details': skip_details,
            'unknown_network_types': unknown,
            'network_type_options': sorted(valid_networks), 'clear_empty': clear_empty}


def _sync_import_dictionaries(prepared):
    """与设备同事务补齐字典；并发同名导入不重复创建，不单独 commit。"""
    from sqlalchemy import func
    dialect = db.session.get_bind().dialect.name
    if dialect == 'postgresql':
        from sqlalchemy.dialects.postgresql import insert
    elif dialect == 'sqlite':
        from sqlalchemy.dialects.sqlite import insert
    else:
        raise ServiceError('当前数据库不支持设备导入字典同步')
    for field, model in (('device_type', DeviceType), ('brand', Brand)):
        names = list(dict.fromkeys(
            item['values'][field] for item in prepared['plan']
            if item['action'] in {'create', 'update'} and item['values'].get(field)))
        if not names:
            continue
        existing = {name for (name,) in db.session.query(model.name).filter(model.name.in_(names))}
        missing = [name for name in names if name not in existing]
        last_order = db.session.query(func.max(model.sort_order)).scalar() or 0
        for offset, name in enumerate(missing, 1):
            db.session.execute(insert(model).values(name=name, sort_order=last_order + offset)
                               .on_conflict_do_nothing(index_elements=['name']))


def execute_device_import(prepared, operator_name=''):
    """在调用方事务中执行已预检的计划。"""
    password_updates = 0
    affected_customers = set()
    # 先把本批次将认领的旧快照补上安装面。否则第一台设备同步位置时，尚未处理的
    # 对面快照仍是未知面，会被执行层的保守冲突规则拦截。
    for item in prepared['plan']:
        reclaim_id = item['row'].get('_reclaim_rack_install_id')
        if not reclaim_id:
            continue
        install = db.session.get(RackInstall, int(reclaim_id))
        if not install or install.device_id is not None:
            raise ServiceError('机柜历史快照已发生变化，请重新预检后导入')
        install.install_side = _rack_side(item['row'].get('location'))
    db.session.flush()
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
            reclaim_id = row.get('_reclaim_rack_install_id')
            if reclaim_id:
                install = db.session.get(RackInstall, int(reclaim_id))
                if not install or install.device_id is not None:
                    raise ServiceError('机柜历史快照已发生变化，请重新预检后导入')
                install.device_id = device.id
                install.manual_name = ''
                install.manual_brand = ''
                install.manual_model = ''
                install.manual_ip = ''
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
                'rack_install_side': row.get('location') or '',
            }
            if clear_empty and 'rack_name' in row.get('_present', set()) and not row.get('rack_name'):
                placement['rack_id'] = None
            _sync_rack_placement(device, placement)
        if device.customer_id:
            affected_customers.add(device.customer_id)
    _sync_import_dictionaries(prepared)
    return {'password_updates': password_updates, 'customer_ids': affected_customers}
