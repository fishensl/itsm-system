# -*- coding: utf-8 -*-
"""批量导出审计摘要，禁止写入导出内容和凭据。"""

_FILTER_KEYS = (
    'search', 'customer_id', 'customer_ids', 'date_from', 'date_to',
    'preset', 'items', 'status', 'category',
)


def export_audit_detail(data, row_count, columns, token=''):
    from utils.json_fields import dumps_json

    filters = {}
    for key in _FILTER_KEYS:
        value = (data or {}).get(key)
        if value in (None, '', []):
            continue
        if isinstance(value, list):
            filters[key] = [str(item)[:64] for item in value[:100]]
        else:
            filters[key] = str(value)[:128]
    payload = {
        'rows': int(row_count),
        'columns': [str(code)[:64] for code in (columns or [])[:100]],
        'filters': filters,
    }
    if token:
        payload['token'] = str(token)[:128]
    return dumps_json(payload)
