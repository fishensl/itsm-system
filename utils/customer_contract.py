# -*- coding: utf-8 -*-
"""客户合同服务期：状态派生 / 过期判断 / 合同联动回填

- 客户表 contract_start_date / contract_end_date 为服务期真源（手动可覆盖）。
- 未设置合同 = 不拦截（存量客户兼容），状态返回「未设置合同」。
- 销售合同（contracts 表执行中/已签）变更时经 sync_from_contract() 回填客户服务期。
"""
from datetime import date

from models import Customer, Contract
from utils.constants import (
    CUSTOMER_CONTRACT_ACTIVE, CUSTOMER_CONTRACT_EXPIRING,
    CUSTOMER_CONTRACT_EXPIRED, CUSTOMER_CONTRACT_NONE,
    CUSTOMER_CONTRACT_REMIND_DAYS,
)


def contract_status(customer):
    """派生客户合同状态：服务中 / 即将到期 / 已过期 / 未设置合同"""
    end = customer.contract_end_date
    if not end:
        return CUSTOMER_CONTRACT_NONE
    today = date.today()
    if end < today:
        return CUSTOMER_CONTRACT_EXPIRED
    if (end - today).days <= CUSTOMER_CONTRACT_REMIND_DAYS:
        return CUSTOMER_CONTRACT_EXPIRING
    return CUSTOMER_CONTRACT_ACTIVE


def contract_expired(customer):
    """客户合同是否已过期（未设置 = 不过期，兼容存量）"""
    end = customer.contract_end_date
    return bool(end and end < date.today())


def contract_remaining_days(customer):
    """剩余天数（负数=已过期 N 天；未设置返回 None）"""
    if not customer.contract_end_date:
        return None
    return (customer.contract_end_date - date.today()).days


def sync_from_contract(contract=None, customer_id=None):
    """销售合同变更后回填客户服务期（客户表为真源）。

    取该客户全部「执行中/已签」合同的 start_date 最小值 / end_date 最大值；
    无有效合同时不覆盖客户手动维护的服务期（避免误清）。
    失败静默（联动失败不阻断合同流程）。
    """
    try:
        target = contract.customer_id if contract else customer_id
        if not target:
            return
        customers = Customer.query.filter_by(id=target).all()
        if not customers:
            return
        cust = customers[0]
        active = (Contract.query
                  .filter(Contract.customer_id == cust.id,
                          Contract.status.in_(['执行中', '已签']),
                          Contract.end_date.isnot(None))
                  .all())
        if not active:
            return
        starts = [c.start_date for c in active if c.start_date]
        ends = [c.end_date for c in active if c.end_date]
        if not ends:
            return
        cust.contract_start_date = min(starts) if starts else cust.contract_start_date
        cust.contract_end_date = max(ends)
    except Exception:
        from flask import current_app
        try:
            current_app.logger.warning('客户合同服务期联动回填失败（非致命）', exc_info=True)
        except Exception:
            pass
