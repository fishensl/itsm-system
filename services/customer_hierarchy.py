# -*- coding: utf-8 -*-
"""客户单位层级推导

把同一类别（如「水利局」）下、同一地级市的客户组织成「市级 → 县级」两层结构。
默认按 region+category 自动推导，Customer.parent_id 非空时手动覆盖。

仅供客户列表、设备列表等渲染层调用，不影响数据库存储。
"""
from collections import OrderedDict

from models import Customer


# ============================ 层级推导 ============================
def build_parent_index(customers):
    """建立 {(parent_region_id_or_self_market, category_id): 市级客户} 索引

    对每个「市级客户」（region_rel 存在且 region_rel.parent_id IS NULL）+
    category_id 非空 → 用 (region_id, category_id) 当 key 入索引。
    同 key 多个时取 id 最小的（稳定）。
    """
    idx = {}
    for c in customers:
        if not c.category_id or not c.region_rel:
            continue
        if c.region_rel.parent_id is not None:
            continue  # 自身是区/县级，跳过
        key = (c.region_rel.id, c.category_id)
        cur = idx.get(key)
        if cur is None or c.id < cur.id:
            idx[key] = c
    return idx


# 兼容旧调用
_build_city_parent_index = build_parent_index


def derive_parent_id(c, by_region_category):
    """返回 c 应折叠到的父客户 id；找不到返回 None。

    优先级：c.parent_id（手动覆盖）> 同类别+父地市的市级客户 > None（顶层）
    防自环：手动 parent_id 指向自身视为无父。
    """
    if c.parent_id and c.parent_id != c.id:
        return c.parent_id
    if not c.region_rel or c.region_rel.parent_id is None:
        return None  # 客户本身就在市级或无地区 → 顶层
    if not c.category_id:
        return None
    key = (c.region_rel.parent_id, c.category_id)
    parent = by_region_category.get(key)
    return parent.id if parent and parent.id != c.id else None


# ============================ 树构建 ============================
def city_of(customer):
    """客户归属的地市名称（与设备列表保持一致的兜底逻辑）"""
    if customer.region_rel and customer.region_rel.parent:
        return customer.region_rel.parent.name
    if customer.region_rel:
        return customer.region_rel.name
    return customer.city or '未分配地市'


# 兼容旧名
_city_of = city_of


def _category_of(customer):
    return customer.category_rel.name if customer.category_rel else '未分类'


def build_flat_nodes(customers):
    """把客户列表组织成「顶层节点 + 子节点」一维列表（不分地市分组）。

    返回 [{'customer': Customer, 'children': [Customer, ...]}, ...]
    - 顶层节点排序：先按客户名（中文按拼音 fallback 到 utf8）稳定
    - 子节点按客户名排序
    """
    parent_index = build_parent_index(customers)
    by_id = {c.id: c for c in customers}

    effective_parent = {}
    for c in customers:
        pid = derive_parent_id(c, parent_index)
        if pid and pid in by_id:
            effective_parent[c.id] = pid

    node_of = {c.id: {'customer': c, 'children': []} for c in customers}
    for cid, pid in effective_parent.items():
        node_of[pid]['children'].append(node_of[cid]['customer'])

    # 子节点按名字排序
    for n in node_of.values():
        n['children'].sort(key=lambda x: x.name)

    # 顶层节点按名字排序
    tops = [node_of[c.id] for c in customers if c.id not in effective_parent]
    tops.sort(key=lambda n: n['customer'].name)
    return tops


def build_city_tree(customers):
    """把客户列表组织成「地市 → 单位类别 → 父单位（含 children）」三段结构。

    返回 OrderedDict[city_name] = OrderedDict[category_name] = [node, ...]
    node = {'customer': Customer, 'children': [Customer, ...]}

    - 市级客户 → 顶层节点
    - 孤儿县级客户（无同类同市市级父）→ 按用户确认，也作为顶层节点（无 children）
    - 县级客户找到父 → 折叠到对应父节点 children 下
    """
    by_id = {c.id: c for c in customers}
    parent_index = build_parent_index(customers)

    # 第一遍：判定每个客户的有效父 id（仅当父也在当前集合内才生效）
    effective_parent = {}
    for c in customers:
        pid = derive_parent_id(c, parent_index)
        if pid and pid in by_id:
            effective_parent[c.id] = pid

    # 第二遍：构造节点
    node_of = {c.id: {'customer': c, 'children': []} for c in customers}
    for cid, pid in effective_parent.items():
        node_of[pid]['children'].append(node_of[cid]['customer'])

    # 第三遍：组织成 city → category → [node]
    tree = OrderedDict()
    # 排序：地市按名字、类别按 sort_order（无 sort_order 时按名字），节点按 id
    sorted_customers = sorted(
        customers,
        key=lambda c: (
            city_of(c),
            (c.category_rel.sort_order if c.category_rel else 0),
            _category_of(c),
            c.id,
        ),
    )
    for c in sorted_customers:
        if c.id in effective_parent:
            continue  # 子节点，跳过顶层
        city = city_of(c)
        cat = _category_of(c)
        tree.setdefault(city, OrderedDict()).setdefault(cat, []).append(node_of[c.id])
    return tree


# ============================ 表单辅助 ============================
def candidate_parents(category_id, exclude_id=None):
    """返回「上级单位」下拉候选：同类别 + 市级（region_rel.parent_id IS NULL）的客户。

    - 没指定 category_id → 返回空（自动推导依赖类别，没类别时手动指定也无意义）
    - exclude_id：编辑场景排除自己 + 自己的全部后代（防自环）
    """
    if not category_id:
        return []
    q = Customer.query.filter(Customer.category_id == category_id)
    if exclude_id:
        descendants = _collect_descendants(exclude_id)
        bad = descendants | {exclude_id}
        q = q.filter(~Customer.id.in_(bad))
    customers = q.all()
    # 只保留市级
    out = []
    for c in customers:
        if c.region_rel and c.region_rel.parent_id is None:
            out.append(c)
    out.sort(key=lambda c: c.name)
    return out


def _collect_descendants(root_id):
    """BFS 收集 root_id 的所有后代 id（递归遍历 children）"""
    seen = set()
    frontier = [root_id]
    while frontier:
        nxt = []
        rows = Customer.query.filter(Customer.parent_id.in_(frontier)).with_entities(Customer.id).all()
        for (cid,) in rows:
            if cid not in seen:
                seen.add(cid)
                nxt.append(cid)
        frontier = nxt
    return seen
