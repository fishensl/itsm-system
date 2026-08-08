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
  result?: string
}

export const FAULT_RESULT_TAG: Record<string, 'primary' | 'success' | 'warning' | 'danger' | 'info'> = {
  已解决: 'success',
  待观察: 'warning',
  未解决: 'danger',
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
  fault_types: { id: number; name: string }[]
  customers: { id: number; name: string; region_id: number | null }[]
  results: string[]
}

export function fetchFaultDicts() {
  return request<FaultDicts>({ url: '/api/dicts/faults', method: 'GET' })
}

export function exportFaults(params: Record<string, unknown>) {
  return request<{ filename: string; content: string }>({
    url: '/api/faults/export',
    method: 'POST',
    data: params,
  })
}
