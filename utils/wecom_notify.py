# -*- coding: utf-8 -*-
"""多渠道通知 - 事件语义与规则种子

事件类型常量 + 默认通知规则（启动种子，幂等）。事件推送点统一走 send_all_channels。
"""
from models import db, NotifyRule

# ==================== 事件类型（后台「通知规则」页即按此配置接收人） ====================
EVENT_TICKET_NEW = 'ticket_new'                    # 工单新建（通知接单工程师+销售）
EVENT_TICKET_ASSIGN = 'ticket_assign'              # 工单派发（通知被指派人）
EVENT_TICKET_COMPLETED = 'ticket_completed'        # 工单完成（主管+销售+老板；markdown 摘要）
EVENT_TICKET_REVIEW_PENDING = 'ticket_review_pending'  # 工单提交审核（部门主管）
EVENT_TICKET_SUSPENDED_TIMEOUT = 'ticket_suspended_timeout'  # 工单挂起超时（工程师+主管+销售）
EVENT_TICKET_PROGRESS = 'ticket_progress'              # 工单处置进展（群通知）
EVENT_INSPECTION_ASSIGN = 'inspection_assign'      # 巡检任务派发（被指派人）
EVENT_INSPECTION_STATUS_CHANGED = 'inspection_status_changed'  # 巡检任务状态变更
EVENT_INSPECTION_REVIEW_PENDING = 'inspection_review_pending'  # 巡检报告待审核（部门主管）
EVENT_CONTRACT_EXPIRING = 'contract_expiring'      # 客户合同到期提醒（关联工程师+销售+admin）
EVENT_CONTRACT_REVIEW = 'contract_review'          # 合同例外申请待审（部门主管+admin）
EVENT_SECURITY = 'security_event'                  # 身份与敏感操作安全事件（admin）
EVENT_BACKUP_FAILURE = 'backup_failure'            # 自动备份失败（admin）

EVENT_LABELS = {
    EVENT_TICKET_NEW: '工单新建',
    EVENT_TICKET_ASSIGN: '工单派发',
    EVENT_TICKET_COMPLETED: '工单完成',
    EVENT_TICKET_REVIEW_PENDING: '工单提交审核',
    EVENT_TICKET_SUSPENDED_TIMEOUT: '工单挂起超时',
    EVENT_TICKET_PROGRESS: '工单处理进展',
    EVENT_INSPECTION_ASSIGN: '巡检任务派发',
    EVENT_INSPECTION_STATUS_CHANGED: '巡检任务状态变更',
    EVENT_INSPECTION_REVIEW_PENDING: '巡检报告待审核',
    EVENT_CONTRACT_EXPIRING: '客户合同到期提醒',
    EVENT_CONTRACT_REVIEW: '合同例外申请',
    EVENT_SECURITY: '安全事件告警',
    EVENT_BACKUP_FAILURE: '自动备份失败',
}

# 默认规则（启动幂等种子）：event_type → 接收角色/用户
DEFAULT_RULES = {
    EVENT_TICKET_NEW: {'roles': ['sales']},
    EVENT_TICKET_ASSIGN: {'roles': []},
    EVENT_TICKET_COMPLETED: {'roles': ['sales']},
    EVENT_TICKET_REVIEW_PENDING: {'roles': []},
    EVENT_TICKET_SUSPENDED_TIMEOUT: {'roles': ['sales']},
    EVENT_TICKET_PROGRESS: {'roles': ['sales']},
    EVENT_INSPECTION_ASSIGN: {'roles': []},
    EVENT_INSPECTION_STATUS_CHANGED: {'roles': []},
    EVENT_INSPECTION_REVIEW_PENDING: {'roles': []},
    EVENT_CONTRACT_EXPIRING: {'roles': ['sales']},
    EVENT_CONTRACT_REVIEW: {'roles': []},
    EVENT_SECURITY: {'roles': ['admin']},
    EVENT_BACKUP_FAILURE: {'roles': ['admin']},
}


# 默认渠道（启动幂等种子；默认停用，管理员填凭据后启用）
DEFAULT_CHANNELS = (
    ('wecom', '企业微信', 1),
    ('dingtalk', '钉钉', 2),
    ('feishu', '飞书', 3),
)


def notification_link(link):
    """将站内相对路径转换为通知客户端可直接访问的完整地址。"""
    value = str(link or '').strip()
    if not value or value.startswith(('https://', 'http://')):
        return value
    if not value.startswith('/'):
        value = '/' + value
    try:
        from flask import current_app, has_request_context, request
        base = (request.host_url.rstrip('/') if has_request_context()
                else current_app.config.get('NOTIFICATION_BASE_URL', '').rstrip('/'))
    except RuntimeError:
        base = ''
    return f'{base}{value}' if base else value


def _line(label, value):
    value = str(value or '').strip()
    return f'> **{label}：**{value}' if value else ''


def _format_utc(value):
    if not value:
        return ''
    from utils.business_time import format_beijing
    return format_beijing(value, '%Y年%m月%d日 %H:%M')


def ticket_notification_content(ticket, actor='', assignee='', progress=''):
    """构造群通知中的工单详情；空字段不输出，避免无意义占位。"""
    customer = getattr(ticket, 'customer_rel', None)
    customer_name = ((getattr(customer, 'name', '') if customer else '') or
                     getattr(ticket, 'customer_name_text', '') or '')
    customer_location = ''
    if customer:
        customer_location = (getattr(customer, 'office_room', '') or
                             getattr(customer, 'map_location', '') or
                             getattr(customer, 'address', '') or
                             getattr(customer, 'office', '') or '')
    reporter = getattr(ticket, 'reporter', '') or ''
    reporter_phone = getattr(ticket, 'reporter_phone', '') or ''
    if reporter and reporter_phone:
        reporter = f'{reporter}（{reporter_phone}）'
    elif reporter_phone:
        reporter = reporter_phone
    lines = [
        _line('用户', customer_name),
        _line('报修联系人', reporter),
        _line('故障时间', _format_utc(getattr(ticket, 'reported_at', None))),
        _line('故障现象', getattr(ticket, 'description', '') or getattr(ticket, 'title', '')),
        _line('故障地点', getattr(ticket, 'fault_location', '') or customer_location),
        _line('前往时间', _format_utc(getattr(ticket, 'visit_at', None))),
        _line('跟进工程师', assignee or getattr(ticket, 'assigned_to', '')),
        _line('处理进展', progress),
        _line('操作人', actor),
    ]
    return '\n'.join(line for line in lines if line)


def inspection_notification_content(task, assignee_name=''):
    """构造巡检派发详情。前往时间未填写时保留任务期限，避免误报具体时刻。"""
    customer = getattr(task, 'customer_rel', None)
    assignee = getattr(task, 'assignee_rel', None)
    lines = [
        _line('巡检地点', getattr(customer, 'name', '') if customer else ''),
        _line('前往时间', _format_utc(getattr(task, 'visit_at', None))),
        _line('巡检工程师', assignee_name or (
            (getattr(assignee, 'realname', '') or getattr(assignee, 'username', ''))
            if assignee else '')),
    ]
    if not getattr(task, 'visit_at', None):
        start = getattr(task, 'scheduled_start', None)
        end = getattr(task, 'scheduled_end', None)
        if start or end:
            lines.append(_line('任务期限', f'{start or "-"} 至 {end or "-"}'))
    return '\n'.join(line for line in lines if line)


def _format_period(start, end):
    if start and end:
        return f'{start} 至 {end}'
    if start:
        return f'{start} 起'
    if end:
        return f'{end} 止'
    return ''


def task_status_notification_content(task, old_status, actor_name=''):
    """构造任务状态变更详情，明确展示三类时效而不混用。"""
    customer = getattr(task, 'customer_rel', None)
    assignee = getattr(task, 'assignee_rel', None)
    actual_start = getattr(task, 'actual_start', None)
    actual_end = getattr(task, 'actual_end', None)
    lines = [
        _line('状态', f'{old_status or "-"} → {getattr(task, "status", "") or "-"}'),
        _line('巡检地点', getattr(customer, 'name', '') if customer else ''),
        _line('巡检工程师', (
            (getattr(assignee, 'realname', '') or getattr(assignee, 'username', ''))
            if assignee else '')),
        _line('合同时效', _format_period(
            getattr(task, 'planned_start', None), getattr(task, 'planned_end', None))),
        _line('任务期限', _format_period(
            getattr(task, 'scheduled_start', None), getattr(task, 'scheduled_end', None))),
        _line('实施开始', actual_start.strftime('%Y年%m月%d日 %H:%M') if actual_start else ''),
        _line('实施结束', actual_end.strftime('%Y年%m月%d日 %H:%M') if actual_end else ''),
        _line('操作人', actor_name),
    ]
    return '\n'.join(line for line in lines if line)


def notify_task_status_changed(task, old_status, actor_name='', actor_user_id=None):
    """任务状态真正变更后向所有启用渠道分发；同值保存不重复通知。"""
    new_status = getattr(task, 'status', '') or ''
    if not old_status or old_status == new_status:
        return 0, 0
    assignee_id = getattr(task, 'assigned_to_user_id', None)
    target_user_ids = [assignee_id] if assignee_id else []
    if not target_user_ids and actor_user_id:
        target_user_ids.append(actor_user_id)
    return wecom_broadcast(
        EVENT_INSPECTION_STATUS_CHANGED,
        f'巡检任务状态：{old_status} → {new_status}｜{getattr(task, "title", "")}',
        task_status_notification_content(task, old_status, actor_name),
        '/app/task-schedule', target_user_ids=target_user_ids, mode='markdown')


def seed_default_notify_channels():
    """幂等种入默认通知渠道（wecom/dingtalk/feishu，默认停用）。

    渠道配置为空导致「通知渠道」页空白：启动时补齐 3 个渠道卡片，
    管理员填写凭据并启用后即可推送。
    """
    from models import NotifyChannelConfig
    for channel_type, name, order in DEFAULT_CHANNELS:
        if NotifyChannelConfig.query.filter_by(channel_type=channel_type).first():
            continue
        db.session.add(NotifyChannelConfig(
            channel_type=channel_type, name=name,
            config_json='{}', is_enabled=False, sort_order=order,
        ))
    db.session.commit()


def seed_default_notify_rules():
    """幂等种入默认通知规则（启动时调用；不覆盖已改过的规则）"""
    from utils.json_fields import dumps_json
    for event_type, recipients in DEFAULT_RULES.items():
        if NotifyRule.query.filter_by(event_type=event_type).first():
            continue
        db.session.add(NotifyRule(
            event_type=event_type,
            label=EVENT_LABELS.get(event_type, event_type),
            is_enabled=True,
            recipients_json=dumps_json(recipients),
        ))
    seed_default_notify_channels()
    db.session.commit()


def wecom_broadcast(event_type, title, content='', link='', target_user_ids=None,
                    mode='text', file_path=None):
    """便捷入口：多渠道分发（内部再套一层 try，绝不让通知影响主流程）"""
    from utils.notify_channels import send_all_channels
    try:
        return send_all_channels(event_type, title, content, notification_link(link), target_user_ids,
                                 mode=mode, file_path=file_path)
    except Exception:
        from flask import current_app
        try:
            current_app.logger.warning('多渠道通知分发异常 event_type=%s', event_type,
                                       exc_info=True)
        except Exception:
            pass
        return 0, 0
