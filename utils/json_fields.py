# -*- coding: utf-8 -*-
"""JSON Text 字段读写边界校验（替代散落的 json.loads or '[]' 裸解析）

约 25 处 db.Text JSON 字段共用此入口：
- 解析失败记日志并返回默认值（不再静默吞掉，也不再出现 len(json_str) 数字符的 bug）
- 序列化统一 ensure_ascii=False（中文可读）
"""
import json

from flask import current_app, has_app_context


def parse_json(text, default=None, field_name=''):
    """解析 JSON 文本字段；失败时记 warning 并返回 default（默认 []）。

    :param text: 数据库存储的 JSON 字符串（可能为 None/''）
    :param default: 解析失败/为空时的返回值，默认 []
    :param field_name: 字段标识（日志定位用，如 'inspection.items_json'）
    """
    if default is None:
        default = []
    if not text:
        return default
    if not isinstance(text, str):
        return text  # 已是对象（容错：调用方误传 dict/list 时直接透传）
    try:
        return json.loads(text)
    except (json.JSONDecodeError, TypeError):
        if has_app_context():
            current_app.logger.warning('JSON 字段解析失败(%s): %r', field_name, text[:120])
        return default


def dumps_json(obj) -> str:
    """序列化对象为 JSON 文本（统一 ensure_ascii=False，中文可读）"""
    return json.dumps(obj, ensure_ascii=False)
