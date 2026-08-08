import request from '@/utils/request'
import type { PageResult } from '@/types'

export interface Customer {
  id: number
  name: string
  contact_person: string
  phone: string
  email: string
  level: string
  city: string
  address: string
  office: string
  office_room: string
  map_location: string
  contract_start_date: string
  contract_end_date: string
  contract_status: string
  contract_remaining_days: number | null
  source: string
  remark: string
  region_id: number | null
  category_id: number | null
  parent_id: number | null
  has_onsite: boolean
  has_onsite_label: string
  onsite_contact: string
  onsite_phone: string
  onsite_office: string
  has_drill: boolean
  inspection_frequency: string
  device_count: number
  category_name: string
  region_name: string
  created_at: string
  extra_fields: { name: string; value: string }[]
  inspection_count?: number
  ticket_count?: number
}

export interface CustomerQuery {
  page?: number
  page_size?: number
  search?: string
  level?: string
  category_id?: number
  region_id?: number
}

export interface CustomerForm {
  name: string
  contact_person: string
  phone: string
  email: string
  region_id: number | null
  category_id: number | null
  level: string
  address: string
  has_onsite: boolean
  onsite_contact: string
  onsite_phone: string
  onsite_office: string
  has_drill: boolean
  remark: string
  contract_start_date?: string
  contract_end_date?: string
  office_room?: string
  map_location?: string
}

export const CUSTOMER_LEVEL_TAG: Record<string, 'primary' | 'success' | 'warning' | 'danger' | 'info'> = {
  核心: 'danger',
  重点: 'warning',
  常规: 'info',
  auto: 'info',
}

/** 客户合同状态标签（服务中绿 / 即将到期黄 / 已过期红 / 未设置灰） */
export const CONTRACT_STATUS_TAG: Record<string, 'primary' | 'success' | 'warning' | 'danger' | 'info'> = {
  服务中: 'success',
  即将到期: 'warning',
  已过期: 'danger',
  未设置合同: 'info',
}

/** 等级值 → 中文显示文本（auto 为「自动（智能定级）」） */
export const CUSTOMER_LEVEL_LABELS: Record<string, string> = {
  auto: '自动',
}

export function fetchCustomers(params: CustomerQuery) {
  return request<PageResult<Customer>>({ url: '/api/customers', method: 'GET', params })
}

export interface CustomerTreeGroup {
  id: number | null
  name: string
  region: boolean
  customer_count: number
  children: Array<Customer & { district: string }>
}

export function fetchCustomerTree(params?: Pick<CustomerQuery, 'search' | 'level' | 'category_id'>) {
  return request<{ tree: CustomerTreeGroup[]; total: number }>({
    url: '/api/customers/tree',
    method: 'GET',
    params,
  })
}

export function exportCustomers(params?: Record<string, unknown>) {
  return request<{ filename: string; content: string }>({
    url: '/api/v2/customers/export',
    method: 'POST',
    data: params || {},
  })
}

export function importCustomers(formData: FormData) {
  return request<{ created: number; unknown_categories: string[] }>({
    url: '/api/v2/customers/import',
    method: 'POST',
    data: formData,
  })
}

export function fetchCustomer(id: number) {
  return request<Customer>({ url: `/api/customers/${id}`, method: 'GET' })
}

export function createCustomer(data: CustomerForm) {
  return request<{ id: number; level: string }>({ url: '/api/customers', method: 'POST', data })
}

export function updateCustomer(id: number, data: CustomerForm) {
  return request<{ id: number; level: string }>({ url: `/api/customers/${id}`, method: 'PUT', data })
}

export function deleteCustomer(id: number) {
  return request<null>({ url: `/api/customers/${id}`, method: 'DELETE' })
}

export interface RegionItem {
  id: number
  name: string
  parent_id: number | null
}

export interface CustomerDicts {
  customer_categories: { id: number; name: string }[]
  regions: RegionItem[]
  levels: string[]
}

export function fetchCustomerDicts() {
  return request<CustomerDicts>({ url: '/api/dicts/customers', method: 'GET' })
}
