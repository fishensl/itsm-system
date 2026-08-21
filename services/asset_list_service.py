# -*- coding: utf-8 -*-
"""资产清单导入服务 — 巡检提交资产清单 Excel 时按 (customer_id, device_name) upsert 设备

列映射与设备管理导入模板对齐（blueprints/asset/devices.py field_mapping），
差异：本服务按客户归属 upsert（更新已有设备字段 + 新增缺失设备），
设备管理手动导入为纯新增。
"""
import os
from flask import current_app
from models import db, Customer, Device
from .base import ServiceError

_FIELD_MAPPING = {
    '所属客户': 'customer_name', '设备名称': 'device_name', '设备类型': 'device_type',
    '品牌': 'brand', '型号': 'model', '序列号': 'serial_number', 'IP地址': 'ip_address',
    '端口': 'port', '登录用户名': 'username', '登录密码': 'password',
    '授权截止日期': 'license_expiry', '授权开始日期': 'license_start', '登录方式': 'login_method',
    '安装位置': 'location', '电源配置': 'power_supply',
    '系统版本': 'os_version', '规则库版本': 'rule_version', '备注': 'remark',
    '是否维修': 'is_maintenance', '是否在用': 'is_in_use',
}


def import_asset_list(file_path, customer_id, operator_name, filename='资产清单.xlsx'):
    """解析资产清单 Excel（已保存的 static 相对路径）并按 (customer_id, device_name) upsert 设备。

    Args:
        file_path: 已保存的 Excel 相对 static 路径（调用方负责落盘）
        customer_id: 归属客户（任务客户）
        operator_name: 操作人
        filename: 展示用文件名
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

    if '设备名称' not in col_map:
        raise ServiceError('Excel 缺少必需列「设备名称」')

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
            payload = dict(
                device_type=row_data.get('device_type', ''),
                brand=row_data.get('brand', ''),
                model=row_data.get('model', ''),
                serial_number=row_data.get('serial_number', ''),
                ip_address=row_data.get('ip_address', ''),
                port=int(row_data.get('port', 22)) if row_data.get('port') else 22,
                username=row_data.get('username', ''),
                login_method=row_data.get('login_method', ''),
                os_version=row_data.get('os_version', ''),
                rule_version=row_data.get('rule_version', ''),
                is_maintenance=row_data.get('is_maintenance', '') in ('是', '1', 'true', 'True'),
                is_in_use=row_data.get('is_in_use', '') in ('是', '1', 'true', 'True'),
                license_expiry=_parse_date(row_data.get('license_expiry')),
                license_start=_parse_date(row_data.get('license_start')),
                remark=row_data.get('remark', ''),
            )
            if '安装位置' in col_map:
                payload['location'] = normalize_device_choice(
                    'location', row_data.get('location'), existing.get(device_name).location
                    if existing.get(device_name) else None)
            if '电源配置' in col_map:
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

    db.session.commit()
    # 刷新客户 device_count/等级冗余（统一入口，全量口径：与删除校验/设备 CRUD 一致）
    try:
        from services.device_service import sync_customer_device_count
        sync_customer_device_count(customer.id)
    except Exception:
        db.session.rollback()
    return {'created': created, 'updated': updated, 'skipped': skipped,
            'errors': errors, 'filename': filename or '资产清单.xlsx'}
