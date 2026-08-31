# -*- coding: utf-8 -*-
"""Fault 故障业务服务"""
from datetime import datetime
from models import db, Fault
from utils.constants import FAULT_OBSERVING, FAULT_RESOLVED
from .base import ServiceError, transaction
from .fault_category_service import resolve_fault_category_path
from utils.business_time import parse_beijing_to_utc


def _parse_dt(value):
    """解析 datetime-local 表单值（%Y-%m-%dT%H:%M），失败返回 None"""
    if not value:
        return None
    for fmt in ('%Y-%m-%dT%H:%M', '%Y-%m-%d %H:%M'):
        try:
            return datetime.strptime(value, fmt)
        except (ValueError, TypeError):
            continue
    return None


@transaction
def create_fault(data, current_user_name):
    """新建故障"""
    title = (data.get('title') or '').strip()
    if not title:
        raise ServiceError('故障标题不能为空')
    category_path, _ = resolve_fault_category_path(
        data.get('category_l1'), data.get('category_l2'), data.get('category_l3'))
    # V28: 客户合同过期门禁（故障记录同样不允许过期客户安排）
    if data.get('customer_id'):
        from models import Customer
        cust = Customer.query.get(int(data['customer_id']))
        if cust is not None:
            from utils.customer_contract import contract_expired
            if contract_expired(cust):
                raise ServiceError('该客户合同已过期，请先提交合同例外申请（部门主管审核）或改用工单创建')
    f = Fault(
        title=title,
        customer_id=int(data['customer_id']) if data.get('customer_id') else None,
        fault_type=data.get('fault_type', ''),
        fault_time=_parse_dt(data.get('fault_time')) or datetime.utcnow(),
        handling_started_at=parse_beijing_to_utc(data.get('handling_started_at')),
        recovery_time=_parse_dt(data.get('recovery_time')),
        result=data.get('result', '已解决'),
        fault_description=data.get('fault_description', ''),
        fault_cause=data.get('fault_cause', ''),
        impact_range=data.get('impact_range', ''),
        solution=data.get('solution', ''),
        handler=data.get('handler', '') or current_user_name,
        # 三级分级分类（前端三级联动提交；fault_type 自由文本兼容历史数据）
        fault_category_level1=category_path[0],
        fault_category_level2=category_path[1],
        fault_category_level3=category_path[2],
    )
    db.session.add(f)
    return f


@transaction
def update_fault(fault_id, data):
    f = Fault.query.get_or_404(fault_id)
    f.title = (data.get('title') or f.title).strip()
    f.customer_id = int(data['customer_id']) if data.get('customer_id') else f.customer_id
    f.fault_type = data.get('fault_type', f.fault_type)
    if data.get('fault_time'):
        f.fault_time = _parse_dt(data['fault_time']) or f.fault_time
    if 'recovery_time' in data:
        f.recovery_time = _parse_dt(data.get('recovery_time'))
    if 'handling_started_at' in data:
        f.handling_started_at = parse_beijing_to_utc(data.get('handling_started_at'))
    f.result = data.get('result', f.result)
    f.fault_description = data.get('fault_description', f.fault_description)
    f.fault_cause = data.get('fault_cause', f.fault_cause)
    f.impact_range = data.get('impact_range', f.impact_range)
    f.solution = data.get('solution', f.solution)
    f.handler = data.get('handler', f.handler)
    if any(k in data for k in ('category_l1', 'category_l2', 'category_l3')):
        category_path, _ = resolve_fault_category_path(
            data.get('category_l1', f.fault_category_level1),
            data.get('category_l2', f.fault_category_level2),
            data.get('category_l3', f.fault_category_level3))
        f.fault_category_level1, f.fault_category_level2, f.fault_category_level3 = category_path
    return f


def sync_fault_from_ticket(ticket, current_user_name, *, resolved=True):
    """将工单处置结果幂等同步到故障记录。

    故障转工单时会预先存在 ``Fault.ticket_id``，此时更新原记录；普通工单
    首次关闭时创建记录。重开工单保留历史记录，但将结果改为待观察并清空恢复时间。
    本函数不独立提交事务，由工单状态迁移事务统一 commit/rollback。
    """
    fault = (Fault.query.filter_by(ticket_id=ticket.id)
             .order_by(Fault.id.asc()).first())
    if fault is None:
        fault = Fault(
            ticket_id=ticket.id,
            title=ticket.title or f'工单 {ticket.number}',
            customer_id=ticket.customer_id,
            fault_time=ticket.created_at or ticket.started_at or datetime.utcnow(),
            created_at=datetime.utcnow(),
        )
        db.session.add(fault)

    fault.title = ticket.title or fault.title
    fault.customer_id = ticket.customer_id
    fault.handler = ticket.assigned_to or current_user_name or fault.handler
    fault.fault_description = ticket.description or fault.fault_description
    fault.fault_cause = ticket.diagnosis or fault.fault_cause
    fault.solution = ticket.solution or fault.solution
    fault.impact_range = ticket.impact_scope or fault.impact_range
    fault.report_file = ticket.report_file or fault.report_file

    category = (
        ticket.fault_category_level3
        or ticket.fault_category_level2
        or ticket.fault_category_level1
        or ''
    )
    if category:
        fault.fault_type = category
    fault.fault_category_level1 = ticket.fault_category_level1 or ''
    fault.fault_category_level2 = ticket.fault_category_level2 or ''
    fault.fault_category_level3 = ticket.fault_category_level3 or ''
    fault.symptoms_json = ticket.symptoms_json or '[]'
    fault.affected_components_json = ticket.affected_components_json or '[]'
    fault.resolution_steps_json = ticket.resolution_steps_json or '[]'
    fault.root_cause_category = ticket.root_cause_category or ''
    fault.severity_level = ticket.severity_level or ''
    fault.impact_scope = ticket.impact_scope or ''
    fault.normalized_tags = ticket.normalized_tags or ''

    if resolved:
        fault.result = FAULT_RESOLVED
        from .ticket_timing_service import ticket_resolution_at
        fault.recovery_time = ticket_resolution_at(ticket) or datetime.utcnow()
        fault.handling_started_at = ticket.started_at or fault.handling_started_at
    else:
        fault.result = FAULT_OBSERVING
        fault.recovery_time = None
    return fault


@transaction
def delete_fault(fault_id):
    f = Fault.query.get_or_404(fault_id)
    # 清理知识库对该故障的引用，避免悬挂外键
    from models import KnowledgeBase
    KnowledgeBase.query.filter_by(related_fault_id=fault_id).update({'related_fault_id': None})
    db.session.delete(f)


@transaction
def convert_fault_to_ticket(fault_id, current_user_name):
    """故障 → 工单（实时转单，替代一次性迁移脚本）。

    幂等：已转单（fault.ticket_id 已存在）拒绝。
    复制故障核心字段到新工单（source_type='故障转单'），回填 Fault.ticket_id 桥接。
    返回新工单。
    """
    f = Fault.query.get_or_404(fault_id)
    if f.ticket_id:
        from models import Ticket
        existing = Ticket.query.get(f.ticket_id)
        if existing:
            raise ServiceError(f'该故障已转工单 #{existing.number}，请勿重复操作')
        # 桥接工单已被删除：允许重新转单
    from services.ticket_service import create_ticket
    t = create_ticket({
        'title': f.title or '故障工单',
        'customer_id': f.customer_id or '',
        'description': f.fault_description or '',
        'priority': '中',
    }, current_user_name)
    # 结构化故障字段同步到工单（Ticket 无 fault_cause 字段，映射到根因分类）
    t.source_type = '故障转单'
    t.fault_category_level1 = f.fault_category_level1 or ''
    t.fault_category_level2 = f.fault_category_level2 or ''
    t.fault_category_level3 = f.fault_category_level3 or ''
    t.root_cause_category = f.root_cause_category or ''
    t.solution = f.solution or ''
    f.ticket_id = t.id
    return t
