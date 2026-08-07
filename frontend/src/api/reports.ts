import request from '@/utils/request'

export type ReportTab = 'all' | 'inspection' | 'fault' | 'ticket' | 'file'

export type ReportRowType = 'inspection' | 'fault' | 'ticket' | 'file'

/** 报告中心统一行：巡检/故障/工单/报告文件四类记录（列表式） */
export interface ReportRow {
  id: number | string
  type: ReportRowType
  customer_id: number | null
  customer_name: string
  title: string
  /** 巡检日期 / 故障时间 / 工单创建时间 / 文件修改时间 */
  date: string
  /** 巡检审核状态 / 故障结果 / 工单状态 / 文件报告类型 */
  status: string
  report_name: string
  report_url: string
  has_report: boolean
  size_display: string
}

export interface ReportStats {
  customers: number
  total: number
}

export interface ReportsData {
  items: ReportRow[]
  total: number
  stats: ReportStats
}

export interface ReportsQuery {
  tab?: ReportTab
  date_from?: string
  date_to?: string
  customer_id?: number
  search?: string
  page?: number
  page_size?: number
}

export function fetchReports(params: ReportsQuery) {
  return request<ReportsData>({ url: '/api/reports', method: 'GET', params })
}

/** 类型中文映射（DataTable valueMap 用） */
export const REPORT_TYPE_MAP: Record<string, string> = {
  inspection: '巡检',
  fault: '故障',
  ticket: '工单',
  file: '报告文件',
}

export const REPORT_TYPE_TAG: Record<string, 'primary' | 'success' | 'warning' | 'danger' | 'info'> = {
  inspection: 'primary',
  fault: 'danger',
  ticket: 'warning',
  file: 'success',
}
