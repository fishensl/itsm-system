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

export interface FaultDicts {
  fault_types: { id: number; name: string }[]
  customers: { id: number; name: string }[]
  results: string[]
}

export function fetchFaultDicts() {
  return request<FaultDicts>({ url: '/api/dicts/faults', method: 'GET' })
}
