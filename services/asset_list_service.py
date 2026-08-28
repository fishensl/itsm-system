# -*- coding: utf-8 -*-
"""资产清单导入服务 — 巡检提交资产清单 Excel 时按 (customer_id, device_name) upsert 设备

列映射与设备管理导入模板对齐（blueprints/asset/devices.py field_mapping），
差异：本服务按客户归属 upsert（更新已有设备字段 + 新增缺失设备），
设备管理手动导入为纯新增。
"""
import os
from flask import current_app
from domain_metadata import get_entity_schema
from models import db, Customer, Device
from utils.json_fields import dumps_json
from .base import ServiceError

_IMPORTABLE_DEVICE_FIELDS = {
    'device_name', 'device_type', 'rack_location', 'location', 'power_supply',
    'brand', 'model', 'serial_number', 'network_type', 'ip_address', 'port',
    'login_method', 'username', 'password', 'interface', 'os_version',
    'rule_version', 'build_date', 'license_start', 'license_expiry',
    'cert_expiry_date', 'is_maintenance', 'is_in_use', 'remark',
}


def _build_field_mapping():
    """导入表头直接复用设备字段注册表，并保留旧导入模板别名。"""
    schema = get_entity_schema('device')
    mapping = {
        field.label: field.key
        for field in schema.fields
        if field.key in _IMPORTABLE_DEVICE_FIELDS
    }
    mapping.update({
        '所属客户': 'customer_name',
        '设备名称': 'device_name',
        '设备类型': 'device_type',
        'IP地址': 'ip_address',
        '授权截止日期': 'license_expiry',
        '授权开始日期': 'license_start',
    })
    return mapping


_FIELD_MAPPING = _build_field_mapping()


def import_asset_list(file_path, customer_id, operator_name, filename='资产清单.xlsx', commit=True):
    """解析资产清单 Excel（已保存的 static 相对路径）并按 (customer_id, device_name) upsert 设备。

    Args:
        file_path: 已保存的 Excel 相对 static 路径（调用方负责落盘）
        customer_id: 归属客户（任务客户）
        operator_name: 操作人
        filename: 展示用文件名
        commit: 是否立即提交。巡检资料上传传 False，使资产导入与提交版本处于同一事务。
    Returns:
        {'created': n, 'updated': n, 'skipped': n, 'errors': [...], 'filename': str}
    Raises:
        ServiceError: 解析失败
    """
    from utils.upload import open_excel
    from utils.crypto import encrypt_password as _ep
    from services.device_service import _parse_date, normalize_device_choice

    customer = Customer.query.get(customer_id)
    if not customer:
        raise ServiceError('客户不存在，无法导入资产清单')

    if not os.path.isfile(os.path.join('static', file_path)):
        raise ServiceError('资产清单文件不存在')
    wb, ws, err = open_excel(os.path.join('static', file_path), app=current_app)
    if err:
        raise ServiceError(err[0] if isinstance(err, (list, tuple)) else str(err))

    col_map = {}
    for idx, cell in enumerate(ws[1]):
        if cell.value:
            col_map[str(cell.value).strip()] = idx

    if 'device_name' not in {
            _FIELD_MAPPING.get(header) for header in col_map}:
        raise ServiceError('Excel 缺少必需列「名称」（旧模板可用「设备名称」）')

    existing = {d.device_name: d for d in Device.query.filter_by(customer_id=customer.id).all()}

    created = updated = skipped = 0
    errors = []
    for row_idx in range(2, ws.max_row + 1):
        row_data = {}
        for cn, idx in col_map.items():
            val = ws.cell(row=row_idx, column=idx + 1).value
            field = _FIELD_MAPPING.get(cn)
            if field:
                row_data[field] = str(val).strip() if val else ''

        device_name = row_data.get('device_name', '')
        if not device_name:
            skipped += 1
            errors.append(f'第{row_idx}行：设备名称为空，跳过')
            continue

        plain_password = row_data.get('password', '')
        try:
            # 只更新 Excel 实际包含的列；资产表不得清空已有账号、版本等字段。
            payload = {}
            for field in (
                    'device_type', 'brand', 'model', 'serial_number',
                    'network_type', 'ip_address', 'username', 'login_method',
                    'os_version', 'rule_version', 'rack_location', 'remark'):
                if field in row_data:
                    payload[field] = row_data[field]
            if 'port' in row_data:
                payload['port'] = int(row_data['port']) if row_data['port'] else 22
            for field in ('license_expiry', 'license_start', 'build_date',
                          'cert_expiry_date'):
                if field in row_data:
                    payload[field] = _parse_date(row_data[field])
            for field in ('is_maintenance', 'is_in_use'):
                if field in row_data:
                    payload[field] = row_data[field] in ('是', '1', 'true', 'True')
            if 'interface' in row_data:
                raw_interfaces = row_data['interface'].replace('，', ',').replace('、', ',')
                payload['interface'] = dumps_json([
                    item.strip() for item in raw_interfaces.split(',') if item.strip()
                ])
            if 'location' in row_data:
                payload['location'] = normalize_device_choice(
                    'location', row_data.get('location'), existing.get(device_name).location
                    if existing.get(device_name) else None)
            if 'power_supply' in row_data:
                payload['power_supply'] = normalize_device_choice(
                    'power_supply', row_data.get('power_supply'))
            if plain_password:
                payload['password_encrypted'] = _ep(plain_password)
        except Exception as e:  # noqa: BLE001
            skipped += 1
            errors.append(f'第{row_idx}行（{device_name}）：{e}')
            continue

        dev = existing.get(device_name)
        if dev:
            for k, v in payload.items():
                setattr(dev, k, v)
            updated += 1
        else:
            dev = Device(customer_id=customer.id, device_name=device_name, **payload)
            db.session.add(dev)
            existing[device_name] = dev
            created += 1

    if commit:
        db.session.commit()
        # 刷新客户 device_count/等级冗余（统一入口，全量口径：与删除校验/设备 CRUD 一致）
        try:
            from services.device_service import sync_customer_device_count
            sync_customer_device_count(customer.id)
        except Exception:
            db.session.rollback()
    return {'created': created, 'updated': updated, 'skipped': skipped,
            'errors': errors, 'filename': filename or '资产清单.xlsx'}
