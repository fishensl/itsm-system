import request from '@/utils/request'
import type { PageResult } from '@/types'

export interface Fault {
  id: number
  title: string
  customer_id: number | null
  customer_name: string
  handler: string
  fault_time: string
  fault_type: string
  fault_category_level1?: string
  fault_category_level2?: string
  fault_category_level3?: string
  fault_category?: string
  result: string
  impact_range: string
  fault_description?: string
  fault_cause?: string
  solution?: string
  recovery_time?: string
  created_at?: string
  ticket_id?: number | null      // S6: 已转工单桥接
  ticket_number?: string          // S6: 已转工单单号
}

export interface FaultQuery {
  page?: number
  page_size?: number
  search?: string
  fault_type?: string
  category_l1?: string
  result?: string
}

export const FAULT_RESULT_TAG: Record<string, 'primary' | 'success' | 'warning' | 'danger' | 'info'> = {
  已解决: 'success',
  待观察: 'warning',
  未解决: 'danger',
}

/** 故障分类树节点（三级） */
export interface FaultCategoryNode {
  id: number
  name: string
  level: number
  parent_id: number | null
  children: FaultCategoryNode[]
}

export function fetchFaults(params: FaultQuery) {
  return request<PageResult<Fault>>({ url: '/api/faults', method: 'GET', params })
}

export function fetchFault(id: number) {
  return request<Fault>({ url: `/api/faults/${id}`, method: 'GET' })
}

export function createFault(data: Record<string, unknown>) {
  return request<{ id: number }>({ url: '/api/faults', method: 'POST', data })
}

export function updateFault(id: number, data: Record<string, unknown>) {
  return request<{ id: number }>({ url: `/api/faults/${id}`, method: 'PUT', data })
}

export function deleteFault(id: number) {
  return request<null>({ url: `/api/faults/${id}`, method: 'DELETE' })
}

export function convertFaultToTicket(id: number) {
  return request<{ ticket_id: number; ticket_number: string }>({
    url: `/api/faults/${id}/convert`,
    method: 'POST',
  })
}

export interface FaultDicts {
  fault_types: FaultCategoryNode[]
  customers: { id: number; name: string; region_id: number | null }[]
  results: string[]
}

export function fetchFaultDicts() {
  return request<FaultDicts>({ url: '/api/dicts/faults', method: 'GET' })
}

// ==================== 故障分类字典 CRUD（三级） ====================
export function fetchFaultCategories() {
  return request<FaultCategoryNode[]>({ url: '/api/fault-categories', method: 'GET' })
}

export function createFaultCategory(data: { name: string; parent_id?: number | null; sort_order?: number }) {
  return request<{ id: number }>({ url: '/api/fault-categories', method: 'POST', data })
}

export function updateFaultCategory(id: number, data: { name?: string; parent_id?: number | null; sort_order?: number }) {
  return request<null>({ url: `/api/fault-categories/${id}`, method: 'PUT', data })
}

export function deleteFaultCategory(id: number) {
  return request<null>({ url: `/api/fault-categories/${id}`, method: 'DELETE' })
}

export function exportFaults(params: Record<string, unknown>) {
  return request<{ filename: string; content: string }>({
    url: '/api/faults/export',
    method: 'POST',
    data: params,
  })
}
