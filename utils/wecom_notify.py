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
EVENT_INSPECTION_ASSIGN = 'inspection_assign'      # 巡检任务派发（被指派人）
EVENT_INSPECTION_REVIEW_PENDING = 'inspection_review_pending'  # 巡检报告待审核（部门主管）
EVENT_CONTRACT_EXPIRING = 'contract_expiring'      # 客户合同到期提醒（关联工程师+销售+admin）
EVENT_CONTRACT_REVIEW = 'contract_review'          # 合同例外申请待审（部门主管+admin）

EVENT_LABELS = {
    EVENT_TICKET_NEW: '工单新建',
    EVENT_TICKET_ASSIGN: '工单派发',
    EVENT_TICKET_COMPLETED: '工单完成',
    EVENT_TICKET_REVIEW_PENDING: '工单提交审核',
    EVENT_TICKET_SUSPENDED_TIMEOUT: '工单挂起超时',
    EVENT_INSPECTION_ASSIGN: '巡检任务派发',
    EVENT_INSPECTION_REVIEW_PENDING: '巡检报告待审核',
    EVENT_CONTRACT_EXPIRING: '客户合同到期提醒',
    EVENT_CONTRACT_REVIEW: '合同例外申请',
}

# 默认规则（启动幂等种子）：event_type → 接收角色/用户
DEFAULT_RULES = {
    EVENT_TICKET_NEW: {'roles': ['sales']},
    EVENT_TICKET_ASSIGN: {'roles': []},
    EVENT_TICKET_COMPLETED: {'roles': ['sales']},
    EVENT_TICKET_REVIEW_PENDING: {'roles': []},
    EVENT_TICKET_SUSPENDED_TIMEOUT: {'roles': ['sales']},
    EVENT_INSPECTION_ASSIGN: {'roles': []},
    EVENT_INSPECTION_REVIEW_PENDING: {'roles': []},
    EVENT_CONTRACT_EXPIRING: {'roles': ['sales']},
    EVENT_CONTRACT_REVIEW: {'roles': []},
}


# 默认渠道（启动幂等种子；默认停用，管理员填凭据后启用）
DEFAULT_CHANNELS = (
    ('wecom', '企业微信', 1),
    ('dingtalk', '钉钉', 2),
    ('feishu', '飞书', 3),
)


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
        return send_all_channels(event_type, title, content, link, target_user_ids,
                                 mode=mode, file_path=file_path)
    except Exception:
        from flask import current_app
        try:
            current_app.logger.warning('多渠道通知分发异常 event_type=%s', event_type,
                                       exc_info=True)
        except Exception:
            pass
        return 0, 0
