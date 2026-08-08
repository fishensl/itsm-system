/**
 * 业务状态单一真源（前端侧），与后端 utils/constants.py 对齐。
 * 注意：存量数据均为中文字符串，常量值必须与后端完全一致（改值=脏数据）。
 */

export type TagType = 'primary' | 'success' | 'warning' | 'danger' | 'info'

// ==================== 工单状态 ====================
export const TICKET_STATUS = {
  PENDING_ASSIGN: '待派单',
  ASSIGNED: '已派单',
  ACCEPTED: '已接单',
  PROCESSING: '处理中',
  SUSPENDED: '已挂起',
  SUBMITTED: '待审核',
  CHECKED: '已验收',
  CLOSED: '已关闭',
  CONTRACT_REVIEW: '合同审批',
} as const

export const TICKET_STATUS_TAG: Record<string, TagType> = {
  待派单: 'danger',
  已派单: 'warning',
  已接单: 'warning',
  处理中: 'primary',
  已挂起: 'warning',
  待审核: 'warning',
  已验收: 'success',
  已关闭: 'info',
  合同审批: 'danger',
}

// ==================== 巡检任务状态 ====================
export const TASK_STATUS = {
  PENDING: '待执行',
  RUNNING: '执行中',
  REVIEWING: '待审核',
  DONE: '已完成',
  CANCELLED: '已取消',
  CONTRACT_REVIEW: '合同审批',
} as const

export const TASK_STATUS_TAG: Record<string, TagType> = {
  待执行: 'warning',
  执行中: 'primary',
  待审核: 'warning',
  已完成: 'success',
  已取消: 'info',
  合同审批: 'danger',
}

// ==================== 巡检记录审核状态 ====================
export const REVIEW_STATUS = {
  DRAFT: '草稿',
  PENDING: '待审核',
  APPROVED: '已通过',
  REJECTED: '已退回',
} as const

export const REVIEW_STATUS_TAG: Record<string, TagType> = {
  草稿: 'info',
  待审核: 'warning',
  已通过: 'success',
  已退回: 'danger',
}

// ==================== 巡检记录总体状态 ====================
export const OVERALL_STATUS = {
  NORMAL: '正常',
  WARNING: '警告',
  ERROR: '异常',
} as const

export const OVERALL_STATUS_TAG: Record<string, TagType> = {
  正常: 'success',
  警告: 'warning',
  异常: 'danger',
}

// ==================== 商机阶段 ====================
export const OPP_STAGE = {
  INITIAL: '初步接触',
  REQUIREMENT: '需求确认',
  PROPOSAL: '方案报价',
  NEGOTIATION: '商务谈判',
  WON: '成交',
  LOST: '失败',
} as const

export const OPP_STAGE_TAG: Record<string, TagType> = {
  初步接触: 'info',
  需求确认: 'info',
  方案报价: 'primary',
  商务谈判: 'warning',
  成交: 'success',
  失败: 'danger',
}

// ==================== 报价单状态 ====================
export const QUOTATION_STATUS = {
  DRAFT: '草稿',
  SENT: '已发送',
  ACCEPTED: '已接受',
  REJECTED: '已拒绝',
} as const

export const QUOTATION_STATUS_TAG: Record<string, TagType> = {
  草稿: 'info',
  已发送: 'primary',
  已接受: 'success',
  已拒绝: 'danger',
}

// ==================== 合同状态 ====================
export const CONTRACT_STATUS = {
  DRAFT: '草签',
  SIGNED: '已签',
  ACTIVE: '执行中',
  DONE: '已完成',
  TERMINATED: '已终止',
} as const

export const CONTRACT_STATUS_TAG: Record<string, TagType> = {
  草签: 'info',
  已签: 'primary',
  执行中: 'success',
  已完成: 'info',
  已终止: 'danger',
}

// ==================== 项目状态 ====================
export const PROJECT_STATUS = {
  NOT_STARTED: '未启动',
  ACTIVE: '进行中',
  DONE: '已完成',
  PAUSED: '已暂停',
} as const

export const PROJECT_STATUS_TAG: Record<string, TagType> = {
  未启动: 'info',
  进行中: 'primary',
  已完成: 'success',
  已暂停: 'warning',
}

// ==================== 工单优先级 ====================
export const TICKET_PRIORITY_TAG: Record<string, TagType> = {
  紧急: 'danger',
  高: 'warning',
  中: 'info',
  低: 'info',
}

// ==================== 工单来源 ====================
export const TICKET_SOURCE_TYPES = ['客户报修', '巡检发现', '手动创建', '定期维护'] as const

// ==================== 备件单位 ====================
export const SPARE_UNITS = ['个', '块', '条', '根', '套', '台', '盒', '瓶', '米'] as const
