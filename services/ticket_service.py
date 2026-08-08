# -*- coding: utf-8 -*-
"""Ticket 工单业务服务（V21：提交版本化审核闭环）"""
from datetime import datetime, timedelta
from models import db, Ticket, TicketLog, User
from utils.constants import (TICKET_STATUSES, REVIEW_PENDING, TICKET_PENDING_ASSIGN,
                             TICKET_SUSPENDED, TICKET_PROCESSING, TICKET_CONTRACT_REVIEW)
from .base import ServiceError, transaction
from .submission_version_service import add_version, review_version, latest_pending_version


# 状态集合单一真源在 utils/constants.py（此处保留别名兼容旧引用）
TICKET_STATES = TICKET_STATUSES

# 状态机：定义允许的状态转换
TICKET_TRANSITIONS = {
    '待派单': {'已派单', '已关闭'},
    '已派单': {'处理中', '已接单', '待派单', '已关闭'},  # 接单即进入处理中
    '已接单': {'处理中', '已派单', '已关闭'},            # 兼容历史数据
    '处理中': {'待审核', '已关闭', '已挂起'},
    '已挂起': {'处理中', '待审核'},                     # 恢复处理；不可处置则提交审核关闭
    '待审核': {'已验收', '处理中'},  # 审核不通过回退处理中
    '已验收': {'已关闭', '处理中'},  # 客户验收通过关闭，退回则回处理中
    '已关闭': {'处理中'},            # 重开（纠正性操作，调用端需管理员/主管 + 审计）
    '合同审批': {'待派单', '已关闭'},  # 合同例外审核通过→待派单 / 拒绝→已关闭
}


def ticket_completeness(t):
    """工单资料完整性检查：返回 (complete, missing_fields)"""
    missing = []
    if not (t.assigned_to or '').strip():
        missing.append('处理人')
    if not (t.diagnosis or '').strip():
        missing.append('诊断')
    if not (t.solution or '').strip():
        missing.append('方案')
    if not t.report_file:
        missing.append('处理报告')
    if not t.audit_status:
        missing.append('审核')
    if t.status not in ('已验收', '已关闭') and not t.accept_status:
        missing.append('验收')
    return not missing, missing


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


def _next_ticket_number():
    """生成工单号 WO-YYYYMMDD-NNN（当日最大序号 +1）。

    按「序号取最大」替代按 id 取最大：删除当日最后一张工单后不会重号。
    并发同号（当日同秒并发创建）由 PG 唯一约束拦截，路由层捕获 IntegrityError 提示重试。
    """
    from sqlalchemy import func
    today = datetime.now().strftime('%Y%m%d')
    prefix = f'WO-{today}-'
    max_seq = (db.session.query(func.max(
        func.cast(func.substr(Ticket.number, len(prefix) + 1), db.Integer)))
        .filter(Ticket.number.like(prefix + '%')).scalar())
    seq = (max_seq or 0) + 1
    return f'{prefix}{seq:03d}'


@transaction
def create_ticket(data, current_user_name):
    """新建工单"""
    title = (data.get('title') or '').strip()
    if not title:
        raise ServiceError('工单标题不能为空')
    # 自动生成工单号 WO-YYYYMMDD-NNN（当日序号取最大 +1，防删除重号）
    number = _next_ticket_number()
    priority = data.get('priority', '中')
    # S6 SLA：按优先级计算截止时间（高=4h/中=24h/低=72h）
    from utils.constants import SLA_HOURS_BY_PRIORITY, SLA_DEFAULT_HOURS
    sla_hours = SLA_HOURS_BY_PRIORITY.get(priority, SLA_DEFAULT_HOURS)
    # V28: 客户合同过期门禁 → 进入「合同审批」等待部门主管审核
    initial_status = TICKET_PENDING_ASSIGN
    contract_reason = (data.get('contract_exception_reason') or '').strip()
    customer = None
    if data.get('customer_id'):
        from models import Customer
        customer = Customer.query.get(int(data['customer_id']))
    if customer is not None:
        from utils.customer_contract import contract_expired
        if contract_expired(customer):
            if not contract_reason:
                raise ServiceError('该客户合同已过期，请填写合同例外原因后提交（需部门主管审核）')
            initial_status = TICKET_CONTRACT_REVIEW
    t = Ticket(
        number=number,
        title=title,
        customer_id=int(data['customer_id']) if data.get('customer_id') else None,
        customer_name_text=(data.get('customer_name') or '').strip(),
        priority=priority,
        description=data.get('description', ''),
        assigned_to=data.get('assigned_to', ''),
        related_device_id=int(data['related_device_id']) if data.get('related_device_id') else None,
        created_by=current_user_name,
        status=initial_status,
        sla_deadline=datetime.utcnow() + timedelta(hours=sla_hours),
        contract_exception_status='待审核' if initial_status == TICKET_CONTRACT_REVIEW else '',
        contract_exception_reason=contract_reason,
        contract_exception_by=current_user_name,
        contract_exception_at=datetime.utcnow() if initial_status == TICKET_CONTRACT_REVIEW else None,
    )
    db.session.add(t)
    try:
        db.session.flush()
    except Exception:
        db.session.rollback()
        # 工单号唯一约束冲突（并发创建同号）：刷新后再取号重试一次
        try:
            number = _next_ticket_number()
            t.number = number
            db.session.add(t)
            db.session.flush()
        except Exception:
            db.session.rollback()
            raise ServiceError('工单号生成冲突，请重试')
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
    if data.get('customer_name') is not None:
        t.customer_name_text = (data.get('customer_name') or '').strip()
    t.priority = data.get('priority', t.priority)
    t.description = data.get('description', t.description)
    t.assigned_to = data.get('assigned_to', t.assigned_to)
    if 'related_device_id' in data:
        t.related_device_id = int(data['related_device_id']) if data.get('related_device_id') else None
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
    if not assignee:
        raise ServiceError('请填写指派处理人')
    t.assigned_to = assignee
    t.assigned_by = current_user_name
    t.assigned_at = datetime.utcnow()
    _transition(t, '已派单', current_user_name, f'派给 {assignee}')
    return t


@transaction
def accept_ticket(ticket_id, current_user_name, remark=''):
    """接单：直接进入处理中"""
    t = Ticket.query.get_or_404(ticket_id)
    t.accepted_at = datetime.utcnow()
    t.started_at = datetime.utcnow()
    _transition(t, '处理中', current_user_name, remark or '已接单，开始处理')
    return t


@transaction
def submit_ticket(ticket_id, current_user_name, remark='', diagnosis=None, solution=None,
                  report_path='', submitter_user_id=None, note=''):
    """提交处理结果（待审核），同时保存诊断分析与解决方案。

    V21：每次提交追加一条 SubmissionVersion（含诊断/方案/提交备注快照 + 处理报告文件），
    Ticket.report_file 指向最新提交的报告；退回后修改可再次提交，历史版本全部保留。
    note 为工程师提交备注（不便写入报告的实际说明）。
    """
    t = Ticket.query.get_or_404(ticket_id)
    if t.status not in ('处理中', '已挂起'):
        raise ServiceError(f'工单当前状态 "{t.status}" 不能提交审核（仅处理中/已挂起可提交）')
    if diagnosis is not None:
        t.diagnosis = diagnosis
    if solution is not None:
        t.solution = solution
    if report_path:
        t.report_file = report_path
    add_version(
        'ticket', t.id,
        report_file=report_path or '',
        content={'diagnosis': diagnosis or '', 'solution': solution or '', 'remark': note or ''},
        submitted_by_user_id=submitter_user_id,
        review_status=REVIEW_PENDING,
    )
    t.completed_at = datetime.utcnow()
    _transition(t, '待审核', current_user_name, remark)
    return t


@transaction
def audit_ticket(ticket_id, approved, current_user_name, remark='', requirements=''):
    """审核工单：approved=True 转 已验收，False 退回修改转 处理中。

    V21：审核结果/意见/修改要求写回最新待审核版本（完整审核历史），
    Ticket.audit_* 保留最新一轮快捷值（兼容老逻辑）。
    """
    t = Ticket.query.get_or_404(ticket_id)
    if t.status != '待审核':
        raise ServiceError(f'工单当前状态 "{t.status}" 不能审核（仅待审核可审核）')
    target = '已验收' if approved else '处理中'
    t.audit_status = '通过' if approved else '拒绝'
    t.audit_by = current_user_name
    t.audit_at = datetime.utcnow()
    if remark:
        t.audit_comment = remark
    reviewer = User.query.filter_by(username=current_user_name).first()
    pending = latest_pending_version('ticket', t.id)
    if pending:
        review_version(pending.id, approved,
                       reviewer_user_id=reviewer.id if reviewer else None,
                       comment=remark, requirements=requirements)
    _transition(t, target, current_user_name, remark or ('审核通过' if approved else '审核不通过'))
    return t


@transaction
def accept_check_ticket(ticket_id, current_user_name, remark='', approved=True):
    """客户验收：通过则关闭工单，退回则回处理中"""
    t = Ticket.query.get_or_404(ticket_id)
    target = '已关闭' if approved else '处理中'
    t.accept_status = '通过' if approved else '退回'
    t.accept_by = current_user_name
    t.accept_at = datetime.utcnow()
    if remark:
        t.accept_comment = remark
    _transition(t, target, current_user_name, remark or ('客户验收通过' if approved else '客户验收退回'))
    return t


@transaction
def unassign_ticket(ticket_id, current_user_name, remark=''):
    """撤回重派：已派单/已接单 → 待派单（清空处理人，重新调度）"""
    t = Ticket.query.get_or_404(ticket_id)
    t.assigned_to = ''
    t.assigned_by = ''
    t.assigned_at = None
    _transition(t, '待派单', current_user_name, remark or '撤回重派')
    return t


@transaction
def close_ticket(ticket_id, current_user_name, remark=''):
    """关闭工单"""
    t = Ticket.query.get_or_404(ticket_id)
    _transition(t, '已关闭', current_user_name, remark or '关闭工单')
    return t


@transaction
def reopen_ticket(ticket_id, current_user_name, remark=''):
    """重开已关闭工单（纠正性操作，调用端需管理员/主管权限 + 审计）。

    已关闭 → 处理中：清空关闭时间与审核标记，重新进入处理流程。
    """
    t = Ticket.query.get_or_404(ticket_id)
    if t.status != '已关闭':
        raise ServiceError(f'仅已关闭工单可重开（当前状态 "{t.status}"）')
    _transition(t, '处理中', current_user_name, remark or '重开工单')
    return t


# ==================== V28: 工单挂起 / 处置进展 / 合同例外审批 ====================

@transaction
def suspend_ticket(ticket_id, current_user_name, reason=''):
    """挂起工单（采购等待/无法处置等）：暂停处置时效。

    处理中 → 已挂起；记挂起段；SLA 顺延在恢复时统一计算。
    """
    t = Ticket.query.get_or_404(ticket_id)
    if t.status != '处理中':
        raise ServiceError(f'工单当前状态 "{t.status}" 不能挂起（仅处理中可挂起）')
    reason = (reason or '').strip()
    if not reason:
        raise ServiceError('请填写挂起原因（如：等待采购备件到货）')
    from models import TicketSuspend
    db.session.add(TicketSuspend(
        ticket_id=t.id, reason=reason, started_at=datetime.utcnow(),
        operator=current_user_name,
    ))
    t.suspended_at = datetime.utcnow()
    t.suspend_timeout_notified_at = None  # 重新挂起时清除超时提醒游标
    _transition(t, TICKET_SUSPENDED, current_user_name, f'挂起：{reason}')
    return t


@transaction
def resume_ticket(ticket_id, current_user_name, remark=''):
    """恢复工单：累计挂起时长，SLA 截止时间顺延等量时长。

    已挂起 → 处理中。
    """
    t = Ticket.query.get_or_404(ticket_id)
    if t.status != TICKET_SUSPENDED:
        raise ServiceError(f'工单当前状态 "{t.status}" 不能恢复（仅已挂起可恢复）')
    from models import TicketSuspend
    now = datetime.utcnow()
    opened = TicketSuspend.query.filter_by(ticket_id=t.id, ended_at=None) \
        .order_by(TicketSuspend.id.desc()).first()
    suspend_secs = 0
    if opened and opened.started_at:
        suspend_secs = int((now - opened.started_at).total_seconds())
        t.suspended_seconds = (t.suspended_seconds or 0) + suspend_secs
        opened.ended_at = now
    t.suspended_at = None
    t.suspend_timeout_notified_at = None
    # SLA 顺延：挂起期间不计处置时效
    if t.sla_deadline and suspend_secs:
        t.sla_deadline = t.sla_deadline + timedelta(seconds=suspend_secs)
    _transition(t, TICKET_PROCESSING, current_user_name, remark or '恢复处理')
    return t


@transaction
def add_progress(ticket_id, current_user_name, content='', photos=None):
    """追加工单处置进展（工程师/主管/管理员可写；photos 为相对 static 路径列表）"""
    t = Ticket.query.get_or_404(ticket_id)
    content = (content or '').strip()
    if not content and not photos:
        raise ServiceError('请填写处置进展内容或上传现场照片')
    from models import TicketProgress
    from utils.json_fields import dumps_json
    db.session.add(TicketProgress(
        ticket_id=t.id, content=content,
        photos_json=dumps_json([p for p in (photos or []) if p]),
        operator=current_user_name,
    ))
    _record_log(t, '添加处置进展', current_user_name, content[:50])
    return t


@transaction
def contract_review_ticket(ticket_id, approved, reviewer_name, comment=''):
    """合同例外审核：通过 → 待派单（正常流转）；拒绝 → 已关闭。"""
    t = Ticket.query.get_or_404(ticket_id)
    if t.status != TICKET_CONTRACT_REVIEW:
        raise ServiceError(f'工单当前状态 "{t.status}" 不能进行合同例外审核')
    target = TICKET_PENDING_ASSIGN if approved else '已关闭'
    t.contract_exception_status = '通过' if approved else '拒绝'
    if comment:
        t.contract_exception_reason = t.contract_exception_reason + f'\n审核意见：{comment}'
    _transition(t, target, reviewer_name,
                ('合同例外审核通过' if approved else '合同例外审核拒绝') + (f'：{comment}' if comment else ''))
    return t


def ticket_summary_text(t):
    """工单完成结构化摘要（企业微信完成通知模板）"""
    from models import Customer
    customer_name = ''
    if t.customer_id:
        c = Customer.query.get(t.customer_id)
        if c:
            customer_name = c.name
    if not customer_name:
        customer_name = t.customer_name_text or ''
    return (
        f'客户：{customer_name}\n'
        f'故障时间：{t.created_at.strftime("%Y-%m-%d %H:%M") if t.created_at else "-"}\n'
        f'故障现象：{t.title or ""}\n'
        f'跟进工程师：{t.assigned_to or "-"}\n'
        f'处理进展：{t.solution or t.diagnosis or "已完成"}'
    )
