/**
 * 业务状态由后端 utils/constants.py 生成，禁止在本文件重复维护。
 * 仅保留不属于状态机的前端录入选项。
 */
export * from './status.generated'

import type { TagType } from './status.generated'

export const TICKET_PRIORITY_TAG: Record<string, TagType> = {
  紧急: 'danger',
  高: 'warning',
  中: 'info',
  低: 'info',
}

// 故障转单是系统派生来源，不作为人工创建工单的可选项。
export const TICKET_SOURCE_TYPES = ['客户报修', '巡检发现', '手动创建', '定期维护'] as const

export const SPARE_UNITS = ['个', '块', '条', '根', '套', '台', '盒', '瓶', '米'] as const
