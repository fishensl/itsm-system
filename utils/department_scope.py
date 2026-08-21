# -*- coding: utf-8 -*-
"""组织树数据范围辅助。

``department`` 范围按“本部门及全部下级部门”解释：父部门可以查看子部门数据，
子部门不会反向继承父部门或兄弟部门。实现一次读取部门关系并在内存中遍历，避免
按层级产生 N+1 查询；异常循环通过 ``seen`` 集合截断。
"""


def department_subtree_ids(department_id):
    """返回包含自身的部门子树 ID 集合；无部门返回空集合。"""
    if not department_id:
        return set()

    from models import Department

    root_id = int(department_id)
    children = {}
    for dept_id, parent_id in Department.query.with_entities(
            Department.id, Department.parent_id).all():
        if parent_id is not None:
            children.setdefault(int(parent_id), []).append(int(dept_id))

    seen = set()
    pending = [root_id]
    while pending:
        current = pending.pop()
        if current in seen:
            continue
        seen.add(current)
        pending.extend(children.get(current, ()))
    return seen
