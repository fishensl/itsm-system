# -*- coding: utf-8 -*-
"""巡检资产清单导入适配层。

设备管理页和巡检资料上传都复用 ``device_import_service`` 的匹配、校验、
额定功率、密码历史和机柜位置规则；本文件只负责把任务客户注入每一行。
"""
import os

from flask import current_app

from models import Customer, Device, db
from services.base import ServiceError
from services.device_import_service import (
    execute_device_import,
    normalize_device_import_cell,
    prepare_device_import,
)
from utils.import_templates import get_import_field_mapping


def import_asset_list(file_path, customer_id, operator_name,
                      filename='资产清单.xlsx', commit=True):
    """按任务客户执行 upsert；任一失败行都会拒绝整批，避免部分资产入库。"""
    from utils.upload import open_excel

    customer = db.session.get(Customer, customer_id)
    if not customer:
        raise ServiceError('客户不存在，无法导入资产清单')
    full_path = os.path.join('static', file_path)
    if not os.path.isfile(full_path):
        raise ServiceError('资产清单文件不存在')
    _wb, ws, error = open_excel(full_path, app=current_app)
    if error:
        raise ServiceError(error[0] if isinstance(error, (list, tuple)) else str(error))

    field_mapping = get_import_field_mapping('device')
    col_map = {
        field_mapping[str(cell.value).strip()]: index
        for index, cell in enumerate(ws[1])
        if cell.value and field_mapping.get(str(cell.value).strip())
    }
    if 'device_name' not in col_map:
        raise ServiceError('Excel 缺少必需列「名称」（旧模板可用「设备名称」）')

    rows = []
    present = set(col_map) | {'customer_name'}
    for row_no in range(2, ws.max_row + 1):
        row = {'_row': row_no, '_present': set(present), 'customer_name': customer.name}
        for field, index in col_map.items():
            value = ws.cell(row=row_no, column=index + 1).value
            row[field] = normalize_device_import_cell(field, value)
        row['customer_name'] = customer.name
        if any(value for key, value in row.items()
               if not key.startswith('_') and key != 'customer_name'):
            rows.append(row)

    accessible_ids = {item[0] for item in Device.query.filter_by(
        customer_id=customer.id).with_entities(Device.id).all()}
    prepared = prepare_device_import(
        rows, {customer.name: customer}, accessible_ids, False,
        mode='upsert', network_mappings={}, clear_empty=False)
    if prepared['counts']['failed']:
        raise ServiceError('资产清单预检失败：' + '；'.join(prepared['errors']))
    result = execute_device_import(prepared, operator_name=operator_name)
    if commit:
        db.session.commit()
        from services.device_service import sync_customer_device_count
        sync_customer_device_count(customer.id)
    return {
        'created': prepared['counts']['create'],
        'updated': prepared['counts']['update'],
        'skipped': prepared['counts']['skipped'] + prepared['counts']['unchanged'],
        'errors': [],
        'filename': filename or '资产清单.xlsx',
        'password_updates': result['password_updates'],
    }
