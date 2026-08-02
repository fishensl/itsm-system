import request from '@/utils/request'

export type ReportTab = 'all' | 'inspection' | 'fault' | 'ticket' | 'file'

export interface ReportItem {
  id: number
  title: string
  inspection_date?: string
  fault_time?: string
  created_at?: string
  number?: string
  result?: string
}

export interface ReportFileItem {
  filename: string
  type: string
  size_display: string
  create_time: string
}

export interface ReportBucket {
  id: number | null
  name: string
  counts: { inspection: number; fault: number; ticket: number; file: number }
  items: {
    inspection: ReportItem[]
    fault: ReportItem[]
    ticket: ReportItem[]
    file: ReportFileItem[]
  }
}

export interface ReportTabStats {
  customers: number
  total: number
}

export interface ReportsData {
  data_order: ReportBucket[]
  tab_stats: Record<ReportTab, ReportTabStats>
}

export interface ReportsQuery {
  tab?: ReportTab
  date_from?: string
  date_to?: string
  customer_id?: number
}

export function fetchReports(params: ReportsQuery) {
  return request<ReportsData>({ url: '/api/reports', method: 'GET', params })
}
