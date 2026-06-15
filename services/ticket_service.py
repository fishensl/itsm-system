# -*- coding: utf-8 -*-
"""Ticket 工单业务服务"""
from datetime import datetime
from models import db, Ticket, TicketLog
from .base import ServiceError, transaction


TICKET_STATES = {
    '待派单',  # pending_assign
    '已派单',  # assigned
    '已接单',  # accepted
    '处理中',  # processing
    '待审核',  # submitted
    '已验收',  # checked
    '已关闭',  # closed
}

# 状态机：定义允许的状态转换
TICKET_TRANSITIONS = {
    '待派单': {'已派单', '已关闭'},
    '已派单': {'已接单', '待派单', '已关闭'},
    '已接单': {'处理中', '已派单', '已关闭'},
    '处理中': {'待审核', '已关闭'},
    '待审核': {'已验收', '处理中'},  # 审核不通过回退
    '已验收': {'已关闭'},
    '已关闭': set(),
}


def _record_log(ticket, action, by_user, remark=''):
    """记录工单状态变更日志"""
    log = TicketLog(
        ticket_id=ticket.id,
        action=action,
        operator=by_user,
        comment=remark,
        created_at=datetime.utcnow(),
    )
    db.session.add(log)


@transaction
def create_ticket(data, current_user_name):
    """新建工单"""
    title = (data.get('title') or '').strip()
    if not title:
        raise ServiceError('工单标题不能为空')
    # 自动生成工单号 WO-YYYYMMDD-NNN
    today = datetime.now().strftime('%Y%m%d')
    prefix = f'WO-{today}-'
    last = Ticket.query.filter(Ticket.number.like(prefix + '%'))\
        .order_by(Ticket.id.desc()).first()
    if last:
        try:
            n = int(last.number.split('-')[-1]) + 1
        except (ValueError, IndexError):
            n = 1
    else:
        n = 1
    number = f'{prefix}{n:03d}'
    t = Ticket(
        number=number,
        title=title,
        customer_id=int(data['customer_id']) if data.get('customer_id') else None,
        priority=data.get('priority', '中'),
        description=data.get('description', ''),
        assigned_to=data.get('assigned_to', ''),
        created_by=current_user_name,
        status='待派单',
    )
    db.session.add(t)
    db.session.flush()
    _record_log(t, '创建工单', current_user_name, '')
    return t


@transaction
def update_ticket(ticket_id, data, current_user_name):
    """更新工单基本信息（不影响状态机）"""
    t = Ticket.query.get_or_404(ticket_id)
    title = (data.get('title') or '').strip()
    if not title:
        raise ServiceError('工单标题不能为空')
    t.title = title
    t.customer_id = int(data['customer_id']) if data.get('customer_id') else t.customer_id
    t.priority = data.get('priority', t.priority)
    t.description = data.get('description', t.description)
    t.assigned_to = data.get('assigned_to', t.assigned_to)
    _record_log(t, '编辑工单', current_user_name, '')
    return t


def _transition(ticket, target_state, current_user_name, remark=''):
    """执行状态机转换"""
    if target_state not in TICKET_STATES:
        raise ServiceError(f'未知状态: {target_state}')
    allowed = TICKET_TRANSITIONS.get(ticket.status, set())
    if target_state not in allowed:
        raise ServiceError(f'工单当前状态 "{ticket.status}" 不允许转到 "{target_state}"')
    old = ticket.status
    ticket.status = target_state
    _record_log(ticket, f'状态变更: {old} → {target_state}', current_user_name, remark)


@transaction
def assign_ticket(ticket_id, assignee, current_user_name, remark=''):
    """派单"""
    t = Ticket.query.get_or_404(ticket_id)
    t.assigned_to = assignee
    _transition(t, '已派单', current_user_name, f'派给 {assignee}')
    return t


@transaction
def accept_ticket(ticket_id, current_user_name, remark=''):
    """接单"""
    t = Ticket.query.get_or_404(ticket_id)
    _transition(t, '已接单', current_user_name, remark)
    return t


@transaction
def submit_ticket(ticket_id, current_user_name, remark=''):
    """提交处理结果（待审核）"""
    t = Ticket.query.get_or_404(ticket_id)
    _transition(t, '待审核', current_user_name, remark)
    return t


@transaction
def audit_ticket(ticket_id, approved, current_user_name, remark=''):
    """审核工单：approved=True 转 已验收，False 回退 处理中"""
    t = Ticket.query.get_or_404(ticket_id)
    target = '已验收' if approved else '处理中'
    _transition(t, target, current_user_name, remark or ('审核通过' if approved else '审核不通过'))
    return t


@transaction
def accept_check_ticket(ticket_id, current_user_name, remark=''):
    """客户验收（已验收 状态）"""
    t = Ticket.query.get_or_404(ticket_id)
    _transition(t, '已验收', current_user_name, remark or '客户验收通过')
    return t


@transaction
def close_ticket(ticket_id, current_user_name, remark=''):
    """关闭工单"""
    t = Ticket.query.get_or_404(ticket_id)
    _transition(t, '已关闭', current_user_name, remark or '关闭工单')
    return t
