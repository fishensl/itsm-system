/** 通用中文标签映射（英文枚举值 → 中文显示文本） */

/** 内置角色码 → 中文（对齐后端 utils/permission.py ROLE_LABELS） */
export const ROLE_LABELS: Record<string, string> = {
  admin: '系统管理员',
  operator: '运维工程师',
  sales: '销售人员',
  viewer: '查看者',
}

export const ROLE_TAG: Record<string, 'danger' | 'primary' | 'warning' | 'info'> = {
  admin: 'danger',
  operator: 'primary',
  sales: 'warning',
  viewer: 'info',
}

/** 布尔值显示文本（DataTable valueMap 键为 String 化后的 'true'/'false'） */
export const BOOL_LABELS: Record<string, string> = {
  true: '是',
  false: '否',
}

/** 启用/停用 */
export const ACTIVE_LABELS: Record<string, string> = {
  true: '启用',
  false: '停用',
}

/** 在用/停用 */
export const IN_USE_LABELS: Record<string, string> = {
  true: '在用',
  false: '停用',
}

/** 审计动作码 → 中文（覆盖 blueprints 全部 audit_log 写入点） */
export const AUDIT_ACTION_LABELS: Record<string, string> = {
  'device:delete': '删除设备',
  'device:reveal': '查看设备密码',
  'ticket:delete': '删除工单',
  'customer:delete': '删除客户',
  'user:create': '创建用户',
  'user:update': '更新用户',
  'user:delete': '删除用户',
  'system:ui_version': '切换默认界面',
}

/** 审计对象类型 → 中文 */
export const AUDIT_TARGET_LABELS: Record<string, string> = {
  device: '设备',
  user: '用户',
  ticket: '工单',
  customer: '客户',
  system: '系统',
}

/** 权限码域 → 中文分组名（权限矩阵分组行） */
export const PERM_DOMAIN_LABELS: Record<string, string> = {
  ai: 'AI 集成',
  category: '类别',
  contract_auto: '合同自动化',
  customer: '客户',
  dashboard: '工作台',
  department: '部门',
  device: '设备',
  draft: '草稿',
  fault: '故障',
  inspection: '巡检',
  kb: '知识库',
  permission: '权限',
  region: '地区',
  report: '报告',
  sales: '销售',
  spare: '备件',
  task: '任务',
  ticket: '工单',
  topology: '拓扑',
  user: '用户',
}
