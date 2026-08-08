# -*- coding: utf-8 -*-
"""客户下拉候选裁剪（防批量枚举客户名单）

工单/巡检/故障/备件等下拉字典只返回当前用户可见的客户候选：
- admin 或拥有 customer:manage（客户管理者，如 sales）→ 全量 id+name；
- 其余角色（工程师等）→ 仅 customer_engineers 直接关联客户，无关联返回空
  （前端提示「请向管理员申请关联客户」）。
下拉候选仅含 id/name/region_id，不含电话/地址等敏感字段（敏感字段由
customer:manage 权限页独享）。
"""


def customer_dropdown_options(user):
    """按用户返回客户下拉候选（[{id, name, region_id, contract_status}, ...]）

    附 contract_status 供前端在创建工单/巡检时提示合同过期。
    """
    from models import Customer
    from utils.permission import get_user_permissions
    from utils.customer_contract import contract_status
    perms = get_user_permissions(user)
    if 'customer:manage' in perms:
        rows = Customer.query.order_by(Customer.name).all()
    else:
        cust_ids = [c.id for c in user.customers] if getattr(user, 'customers', None) else []
        if not cust_ids:
            return []
        rows = Customer.query.filter(Customer.id.in_(cust_ids)).order_by(Customer.name).all()
    return [{'id': c.id, 'name': c.name, 'region_id': c.region_id,
             'contract_status': contract_status(c),
             'contract_end_date': c.contract_end_date.isoformat() if c.contract_end_date else ''}
            for c in rows]
