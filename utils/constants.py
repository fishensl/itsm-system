# -*- coding: utf-8 -*-
"""业务状态常量（单一真源，替代散落的裸字符串）

注意：存量数据均为中文字符串，常量值必须与之完全一致（改值=脏数据）。
service 层写入边界应使用这些常量与校验函数，防止拼写错误入库。
"""

# ==================== 工单状态（状态机见 services/ticket_service） ====================
TICKET_PENDING_ASSIGN = '待派单'
TICKET_ASSIGNED = '已派单'
TICKET_ACCEPTED = '已接单'
TICKET_PROCESSING = '处理中'
TICKET_SUBMITTED = '待审核'
TICKET_CHECKED = '已验收'
TICKET_CLOSED = '已关闭'
TICKET_STATUSES = frozenset({
    TICKET_PENDING_ASSIGN, TICKET_ASSIGNED, TICKET_ACCEPTED,
    TICKET_PROCESSING, TICKET_SUBMITTED, TICKET_CHECKED, TICKET_CLOSED,
})

# ==================== 巡检任务状态 ====================
TASK_PENDING = '待执行'
TASK_RUNNING = '执行中'
TASK_DONE = '已完成'
TASK_CANCELLED = '已取消'
TASK_STATUSES = frozenset({TASK_PENDING, TASK_RUNNING, TASK_DONE, TASK_CANCELLED})

# ==================== 巡检记录审核状态 ====================
REVIEW_DRAFT = ''           # 草稿（未提交）
REVIEW_PENDING = '待审核'
REVIEW_APPROVED = '已通过'
REVIEW_REJECTED = '已退回'
REVIEW_STATUSES = frozenset({REVIEW_DRAFT, REVIEW_PENDING, REVIEW_APPROVED, REVIEW_REJECTED})

# ==================== 商机阶段 ====================
OPP_STAGE_INITIAL = '初步接触'
OPP_STAGE_REQUIREMENT = '需求确认'
OPP_STAGE_PROPOSAL = '方案报价'
OPP_STAGE_NEGOTIATION = '商务谈判'
OPP_STAGE_WON = '成交'
OPP_STAGE_LOST = '失败'
OPP_STAGES = (OPP_STAGE_INITIAL, OPP_STAGE_REQUIREMENT, OPP_STAGE_PROPOSAL,
              OPP_STAGE_NEGOTIATION, OPP_STAGE_WON, OPP_STAGE_LOST)

# ==================== 报价单状态 ====================
QUOTATION_STATUSES = frozenset({'草稿', '已发送', '已接受', '已拒绝'})

# ==================== 合同状态 ====================
CONTRACT_DRAFT = '草签'
CONTRACT_SIGNED = '已签'
CONTRACT_ACTIVE = '执行中'
CONTRACT_DONE = '已完成'
CONTRACT_TERMINATED = '已终止'
CONTRACT_STATUSES = frozenset({
    CONTRACT_DRAFT, CONTRACT_SIGNED, CONTRACT_ACTIVE, CONTRACT_DONE, CONTRACT_TERMINATED,
})

# ==================== 项目状态 ====================
PROJECT_NOT_STARTED = '未启动'
PROJECT_ACTIVE = '进行中'
PROJECT_DONE = '已完成'
PROJECT_PAUSED = '已暂停'
PROJECT_STATUSES = frozenset({PROJECT_NOT_STARTED, PROJECT_ACTIVE, PROJECT_DONE, PROJECT_PAUSED})

# ==================== 采集任务状态 ====================
COLLECT_PENDING = 'pending'
COLLECT_RUNNING = 'running'
COLLECT_SUCCESS = 'success'
COLLECT_FAILED = 'failed'
COLLECT_STATUSES = frozenset({COLLECT_PENDING, COLLECT_RUNNING, COLLECT_SUCCESS, COLLECT_FAILED})


def is_valid_status(value, allowed) -> bool:
    """校验状态值是否在允许集合内（service 层写入边界使用）"""
    return value in allowed
