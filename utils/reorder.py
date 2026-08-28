# -*- coding: utf-8 -*-
"""设置页批量排序校验：一次事务、全量 ID、树形资源仅限同级。"""


def parse_ids(raw_ids):
    try:
        ids = [int(value) for value in (raw_ids or [])]
    except (TypeError, ValueError) as exc:
        raise ValueError('排序参数无效') from exc
    if not ids or len(ids) != len(set(ids)):
        raise ValueError('排序项不能为空或重复')
    return ids


def reorder_all(model, raw_ids):
    ids = parse_ids(raw_ids)
    current = model.query.order_by(model.sort_order, model.id).all()
    old_ids = [item.id for item in current]
    if set(ids) != set(old_ids):
        raise ValueError('排序必须包含当前资源的全部项目')
    by_id = {item.id: item for item in current}
    for index, item_id in enumerate(ids, 1):
        by_id[item_id].sort_order = index * 10
    return old_ids, ids


def reorder_siblings(model, raw_ids, parent_id):
    ids = parse_ids(raw_ids)
    current = model.query.filter_by(parent_id=parent_id).order_by(
        model.sort_order, model.id).all()
    old_ids = [item.id for item in current]
    if set(ids) != set(old_ids):
        raise ValueError('树形资源只能在同一父节点内排序，且必须包含全部同级项目')
    by_id = {item.id: item for item in current}
    for index, item_id in enumerate(ids, 1):
        by_id[item_id].sort_order = index * 10
    return old_ids, ids
