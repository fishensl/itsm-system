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
TICKET_SUSPENDED = '已挂起'
TICKET_SUBMITTED = '待审核'
TICKET_CHECKED = '已验收'
TICKET_CLOSED = '已关闭'
TICKET_CONTRACT_REVIEW = '合同审批'   # V28: 客户合同过期时的例外审批态
TICKET_STATUSES = frozenset({
    TICKET_PENDING_ASSIGN, TICKET_ASSIGNED, TICKET_ACCEPTED,
    TICKET_PROCESSING, TICKET_SUSPENDED, TICKET_SUBMITTED, TICKET_CHECKED,
    TICKET_CLOSED, TICKET_CONTRACT_REVIEW,
})

# ==================== 巡检任务状态 ====================
TASK_PENDING = '待执行'
TASK_RUNNING = '执行中'
TASK_REVIEWING = '待审核'
TASK_DONE = '已完成'
TASK_CANCELLED = '已取消'
TASK_CONTRACT_REVIEW = '合同审批'   # V28: 客户合同过期时的例外审批态
TASK_STATUSES = frozenset({TASK_PENDING, TASK_RUNNING, TASK_REVIEWING, TASK_DONE,
                           TASK_CANCELLED, TASK_CONTRACT_REVIEW})
# 看板排序优先级：逾期最前 → 执行中 → 待审核 → 待执行 → 已完成 → 已取消（值越小越靠前）
TASK_SORT_PRIORITY = {TASK_RUNNING: 1, TASK_REVIEWING: 2, TASK_PENDING: 3,
                      TASK_DONE: 4, TASK_CANCELLED: 5, TASK_CONTRACT_REVIEW: 6}
# 任务状态机转换表（key=当前状态, value=允许的下一状态集合）
TASK_TRANSITIONS = {
    TASK_PENDING: {TASK_RUNNING, TASK_CANCELLED},
    TASK_RUNNING: {TASK_REVIEWING, TASK_CANCELLED},
    TASK_REVIEWING: {TASK_RUNNING, TASK_DONE},
    TASK_DONE: set(),
    TASK_CANCELLED: set(),
    TASK_CONTRACT_REVIEW: {TASK_PENDING, TASK_CANCELLED},  # 审核通过→待执行 / 拒绝→已取消
}

# ==================== 巡检记录审核状态 ====================
REVIEW_DRAFT = ''           # 草稿（未提交）
REVIEW_PENDING = '待审核'
REVIEW_APPROVED = '已通过'
REVIEW_REJECTED = '已退回'
REVIEW_STATUSES = frozenset({REVIEW_DRAFT, REVIEW_PENDING, REVIEW_APPROVED, REVIEW_REJECTED})

# ==================== 巡检记录总体状态 ====================
OVERALL_STATUSES = frozenset({'正常', '警告', '异常'})

# ==================== 商机阶段 ====================
OPP_STAGE_INITIAL = '初步接触'
OPP_STAGE_REQUIREMENT = '需求确认'
OPP_STAGE_PROPOSAL = '方案报价'
OPP_STAGE_NEGOTIATION = '商务谈判'
OPP_STAGE_WON = '成交'
OPP_STAGE_LOST = '失败'
OPP_STAGES = (OPP_STAGE_INITIAL, OPP_STAGE_REQUIREMENT, OPP_STAGE_PROPOSAL,
              OPP_STAGE_NEGOTIATION, OPP_STAGE_WON, OPP_STAGE_LOST)
# 商机阶段转换表（S6：顺序推进，终态不可回退；业务附加校验见 sales_service）
OPP_TRANSITIONS = {
    OPP_STAGE_INITIAL: {OPP_STAGE_REQUIREMENT, OPP_STAGE_WON, OPP_STAGE_LOST},
    OPP_STAGE_REQUIREMENT: {OPP_STAGE_PROPOSAL, OPP_STAGE_WON, OPP_STAGE_LOST},
    OPP_STAGE_PROPOSAL: {OPP_STAGE_NEGOTIATION, OPP_STAGE_WON, OPP_STAGE_LOST},
    OPP_STAGE_NEGOTIATION: {OPP_STAGE_WON, OPP_STAGE_LOST},
    OPP_STAGE_WON: set(),
    OPP_STAGE_LOST: set(),
}

# ==================== 报价单状态 ====================
QUOTATION_STATUSES = frozenset({'草稿', '已发送', '已接受', '已拒绝'})
# 报价单转换表（S6：草稿→已发送→{已接受,已拒绝}；终态不可回退）
QUOTATION_TRANSITIONS = {
    '草稿': {'已发送', '已接受', '已拒绝'},
    '已发送': {'已接受', '已拒绝'},
    '已接受': set(),
    '已拒绝': set(),
}

# ==================== 合同状态 ====================
CONTRACT_DRAFT = '草签'
CONTRACT_SIGNED = '已签'
CONTRACT_ACTIVE = '执行中'
CONTRACT_DONE = '已完成'
CONTRACT_TERMINATED = '已终止'
CONTRACT_STATUSES = frozenset({
    CONTRACT_DRAFT, CONTRACT_SIGNED, CONTRACT_ACTIVE, CONTRACT_DONE, CONTRACT_TERMINATED,
})
# 合同状态转换表（S6：草签→已签→执行中→{已完成,已终止}；终态不可回退）
CONTRACT_TRANSITIONS = {
    CONTRACT_DRAFT: {CONTRACT_SIGNED, CONTRACT_ACTIVE, CONTRACT_TERMINATED},
    CONTRACT_SIGNED: {CONTRACT_ACTIVE, CONTRACT_TERMINATED},
    CONTRACT_ACTIVE: {CONTRACT_DONE, CONTRACT_TERMINATED},
    CONTRACT_DONE: set(),
    CONTRACT_TERMINATED: set(),
}

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


# ==================== 工单来源类型 ====================
TICKET_SOURCE_MANUAL = '手动创建'
TICKET_SOURCE_FAULT = '故障转单'
TICKET_SOURCE_TYPES = frozenset({
    TICKET_SOURCE_MANUAL, '客户报修', '巡检发现', '定期维护', TICKET_SOURCE_FAULT,
})

# ==================== SLA 阈值（按优先级 → 处理小时数） ====================
SLA_HOURS_BY_PRIORITY = {'高': 4, '中': 24, '低': 72}
SLA_DEFAULT_HOURS = 24

# ==================== 巡检审核超时提醒 ====================
REVIEW_TIMEOUT_DAYS = 3   # 提交审核后 N 天未审核 → 提醒部门主管 + admin

# ==================== 客户合同服务期（V28） ====================
CUSTOMER_CONTRACT_ACTIVE = '服务中'
CUSTOMER_CONTRACT_EXPIRING = '即将到期'
CUSTOMER_CONTRACT_EXPIRED = '已过期'
CUSTOMER_CONTRACT_NONE = '未设置合同'
CUSTOMER_CONTRACT_STATUSES = frozenset({
    CUSTOMER_CONTRACT_ACTIVE, CUSTOMER_CONTRACT_EXPIRING,
    CUSTOMER_CONTRACT_EXPIRED, CUSTOMER_CONTRACT_NONE,
})
CUSTOMER_CONTRACT_REMIND_DAYS = 30   # 合同到期前 N 天 → 提前提醒

# ==================== 工单挂起超时提醒（V28） ====================
SUSPEND_TIMEOUT_DAYS = 2   # 工单挂起超 N 天未恢复 → 提醒工程师/主管/销售
