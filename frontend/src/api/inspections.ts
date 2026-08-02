import request from '@/utils/request'
import type { PageResult } from '@/types'

export interface Inspection {
  id: number
  title: string
  customer_id: number | null
  customer_name: string
  inspection_date: string
  overall_status: string
  review_status: string
  inspector_name: string
  report_file: boolean
  report_label: string
  location: string
  conclusion: string
  content_json: unknown[]
  field_values_json: Record<string, unknown>
  sections_json: Record<string, unknown>
  review_comment: string
  reviewed_at: string
  created_at: string
}

export interface InspectionQuery {
  page?: number
  page_size?: number
  search?: string
  status?: string
  review_status?: string
  customer_id?: number
}

export const OVERALL_STATUS_TAG: Record<string, 'primary' | 'success' | 'warning' | 'danger' | 'info'> = {
  正常: 'success',
  警告: 'warning',
  异常: 'danger',
  待审核: 'warning',
}

export const REVIEW_STATUS_TAG: Record<string, 'primary' | 'success' | 'warning' | 'danger' | 'info'> = {
  草稿: 'info',
  待审核: 'warning',
  已通过: 'success',
  已退回: 'danger',
}

export function fetchInspections(params: InspectionQuery) {
  return request<PageResult<Inspection>>({ url: '/api/inspections', method: 'GET', params })
}

export function fetchInspection(id: number) {
  return request<Inspection>({ url: `/api/inspections/${id}`, method: 'GET' })
}

export function createInspection(data: Record<string, unknown>) {
  return request<{ id: number }>({ url: '/api/inspections', method: 'POST', data })
}

export function updateInspection(id: number, data: Record<string, unknown>) {
  return request<{ id: number }>({ url: `/api/inspections/${id}`, method: 'PUT', data })
}

export function deleteInspection(id: number) {
  return request<null>({ url: `/api/inspections/${id}`, method: 'DELETE' })
}

export function submitInspection(id: number) {
  return request<null>({ url: `/api/inspections/${id}/submit`, method: 'POST' })
}

export function reviewInspection(id: number, approved: boolean, remark?: string) {
  return request<null>({ url: `/api/inspections/${id}/review`, method: 'POST', data: { approved, remark } })
}

export interface InspectionDicts {
  customers: { id: number; name: string }[]
  inspectors: { user_id: number; name: string }[]
  overall_statuses: string[]
  review_statuses: string[]
}

export function fetchInspectionDicts() {
  return request<InspectionDicts>({ url: '/api/dicts/inspections', method: 'GET' })
}
