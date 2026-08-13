# -*- coding: utf-8 -*-
"""客户与设备的数据可见范围。

权限码回答“能否进入功能”，本模块回答“进入后能看到哪些客户数据”：

- admin 或 scope=all：全部客户；
- scope=department：本人及同部门活跃用户在 customer_engineers 中关联的客户；
- scope=self（以及没有部门的 department 用户）：仅本人直接关联客户。

受限用户没有客户关联时返回空集，绝不回退到全量数据。下拉候选只返回业务所需
的非敏感字段；列表、详情、搜索、导出与设备 API 复用同一套范围判断。
"""

_observed_scope_signatures = set()


def has_full_customer_scope(user) -> bool:
    """当前用户是否拥有全量客户数据范围。"""
    from utils.permission import get_user_scope

    if not user or not getattr(user, 'is_authenticated', False):
        return False
    return get_user_scope(user) == 'all'


def _configured_customer_ids(user):
    """按用户配置计算客户 ID；不受分阶段发布开关影响。"""
    if has_full_customer_scope(user):
        return None
    if not user or not getattr(user, 'is_authenticated', False):
        return set()

    from models import User, customer_engineers, db
    from utils.permission import get_user_scope

    user_ids = [user.id]
    if get_user_scope(user) == 'department' and getattr(user, 'department_id', None):
        user_ids = list(db.session.scalars(
            db.select(User.id).where(
                User.department_id == user.department_id,
                User.is_active.is_(True),
            )
        ))
    return set(db.session.scalars(
        db.select(customer_engineers.c.customer_id)
        .where(customer_engineers.c.engineer_id.in_(user_ids))
        .distinct()
    ))


def visible_customer_ids(user):
    """返回当前实际生效的客户 ID；``None`` 表示暂不强制过滤。"""
    ids = _configured_customer_ids(user)
    if ids is None:
        return None
    from flask import current_app
    if current_app.config.get('CUSTOMER_SCOPE_ENFORCE', False):
        return ids

    # 观测期不改变新增的列表/详情结果，但每进程只记录一次稳定摘要，避免刷日志和泄露 ID。
    signature = (getattr(user, 'id', None), getattr(user, 'scope', None), len(ids))
    if signature not in _observed_scope_signatures:
        _observed_scope_signatures.add(signature)
        current_app.logger.info(
            '客户数据范围处于观测模式: user_id=%s scope=%s configured_customer_count=%s',
            signature[0], signature[1], signature[2])
    return None


def apply_customer_scope(query, model_or_column, user):
    """将客户范围施加到 SQLAlchemy 查询。

    ``model_or_column`` 可传 ``Customer``（使用 ``id``）或 ``Device`` 等具有
    ``customer_id`` 字段的模型，也可直接传列对象。
    """
    ids = visible_customer_ids(user)
    if ids is None:
        return query
    column = model_or_column
    if hasattr(model_or_column, 'customer_id'):
        column = model_or_column.customer_id
    elif hasattr(model_or_column, 'id'):
        column = model_or_column.id
    if not ids:
        return query.filter(column.in_([]))
    return query.filter(column.in_(ids))


def can_access_customer(user, customer_id) -> bool:
    """判断客户 ID 是否在用户数据范围内。"""
    if customer_id is None:
        return has_full_customer_scope(user)
    ids = visible_customer_ids(user)
    return ids is None or int(customer_id) in ids


def require_customer_access(user, customer_id) -> None:
    """越出客户范围时以 404 隐藏对象是否存在。"""
    if not can_access_customer(user, customer_id):
        from flask import abort
        abort(404)


def require_device_access(user, device) -> None:
    """对设备对象执行所属客户范围检查。"""
    require_customer_access(user, getattr(device, 'customer_id', None))


def customer_dropdown_options(user):
    """按已配置关联返回客户下拉候选；观测期也不扩大既有下拉范围。"""
    from models import Customer
    from utils.customer_contract import contract_status

    ids = _configured_customer_ids(user)
    query = Customer.query
    if ids is not None:
        query = query.filter(Customer.id.in_(ids))
    rows = query.order_by(Customer.name).all()
    return [{
        'id': c.id,
        'name': c.name,
        'region_id': c.region_id,
        'contract_status': contract_status(c),
        'contract_end_date': c.contract_end_date.isoformat() if c.contract_end_date else '',
    } for c in rows]
