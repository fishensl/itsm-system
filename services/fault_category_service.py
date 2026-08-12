# -*- coding: utf-8 -*-
"""故障三级分类的统一校验与叶子节点解析。"""

from .base import ServiceError


def resolve_fault_category_path(level1, level2, level3):
    """规范化三级分类并返回 ``((l1, l2, l3), leaf_id)``。

    分类允许为空以兼容历史 API；一旦填写任意一级，就必须完整选择到现有的三级
    叶子节点，避免列表、详情和统计出现半截分类。
    """
    path = tuple(str(value or '').strip() for value in (level1, level2, level3))
    if not any(path):
        return path, None
    if not all(path):
        raise ServiceError('故障分类必须选择完整的一级、二级、三级分类')

    from models import FaultType

    node1 = FaultType.query.filter_by(name=path[0], parent_id=None, level=1).first()
    node2 = (FaultType.query.filter_by(name=path[1], parent_id=node1.id, level=2).first()
             if node1 else None)
    node3 = (FaultType.query.filter_by(name=path[2], parent_id=node2.id, level=3).first()
             if node2 else None)
    if node3 is None:
        raise ServiceError('所选故障分类不存在或不是三级叶子分类，请重新选择')
    return path, node3.id

