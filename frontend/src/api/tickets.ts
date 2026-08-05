import request from '@/utils/request'
import type { PageResult } from '@/types'
import type { SubmissionVersion } from './inspections'

export { versionReportUrl } from './inspections'

export interface Ticket {
  id: number
  number: string
  title: string
  status: string
  priority: string
  customer_id: number | null
  customer_name: string
  assigned_to: string
  created_by: string
  created_at: string
  fault_category_id: number | null
  severity_level: string
  source_type: string
  diagnosis: string
  solution: string
  description: string
  audit_status: string
  audit_by: string
  audit_at: string
  audit_comment: string
  accept_status: string
  accept_comment: string
  report_file: boolean
  report_name: string
  complete: boolean
  missing_fields: string[]
  assigned_at: string
  accepted_at: string
  completed_at: string
  logs?: TicketLog[]
}

export interface TicketLog {
  action: string
  operator: string
  comment: string
  created_at: string
}

export interface TicketQuery {
  page?: number
  page_size?: number
  search?: string
  status?: string
  priority?: string
  customer_id?: number
  scope?: string
  date_from?: string
  date_to?: string
  incomplete_only?: number
}

export interface TicketActionPayload {
  action: string
  assignee?: string
  remark?: string
  approved?: boolean
  diagnosis?: string
  solution?: string
}

export const TICKET_STATUS_TAG: Record<string, 'primary' | 'success' | 'warning' | 'danger' | 'info'> = {
  待派单: 'danger',
  已派单: 'warning',
  已接单: 'warning',
  处理中: 'primary',
  待审核: 'warning',
  已验收: 'success',
  已关闭: 'info',
}

export function fetchTickets(params: TicketQuery) {
  return request<PageResult<Ticket>>({ url: '/api/tickets', method: 'GET', params })
}

export function fetchTicket(id: number) {
  return request<Ticket>({ url: `/api/tickets/${id}`, method: 'GET' })
}

export function createTicket(data: Record<string, unknown>) {
  return request<{ id: number; number: string }>({ url: '/api/tickets', method: 'POST', data })
}

export function updateTicket(id: number, data: Record<string, unknown>) {
  return request<null>({ url: `/api/tickets/${id}`, method: 'PUT', data })
}

export function deleteTicket(id: number) {
  return request<null>({ url: `/api/tickets/${id}`, method: 'DELETE' })
}

export function ticketAction(id: number, payload: TicketActionPayload) {
  return request<null>({ url: `/api/tickets/${id}/action`, method: 'POST', data: payload })
}

/** 提交处理结果 + 上传处理报告（multipart：action + report_file + diagnosis + solution + remark） */
export function ticketActionSubmit(id: number, formData: FormData) {
  return request<null>({ url: `/api/tickets/${id}/action`, method: 'POST', data: formData })
}

export function fetchTicketVersions(id: number) {
  return request<SubmissionVersion[]>({ url: `/api/tickets/${id}/versions`, method: 'GET' })
}

export interface TicketDicts {
  customers: { id: number; name: string }[]
  fault_types: { id: number; name: string }[]
  statuses: string[]
  priorities: string[]
}

export function fetchTicketDicts() {
  return request<TicketDicts>({ url: '/api/dicts/tickets', method: 'GET' })
}

/** 工单记录导出 URL（SSR，带筛选参数） */
export function ticketExportUrl(params: Record<string, unknown>) {
  const q = new URLSearchParams()
  Object.entries(params).forEach(([k, v]) => {
    if (v !== undefined && v !== null && v !== '') q.set(k, String(v))
  })
  return `/tickets/export?${q.toString()}`
}

export function ticketReportsZipUrl(params: Record<string, unknown>) {
  const q = new URLSearchParams()
  Object.entries(params).forEach(([k, v]) => {
    if (v !== undefined && v !== null && v !== '') q.set(k, String(v))
  })
  return `/tickets/reports-zip?${q.toString()}`
}
