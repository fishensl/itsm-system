import request from '@/utils/request'
import type { PageResult } from '@/types'

export interface Device {
  id: number
  customer_id: number | null
  customer_name: string
  device_name: string
  device_type: string
  brand: string
  model: string
  serial_number: string
  ip_address: string
  port: number
  username: string
  has_password: boolean
  login_method: string
  location: string
  interface: string[]
  os_version: string
  rule_version: string
  is_maintenance: boolean
  is_in_use: boolean
  license_expiry: string
  license_start: string
  license_remaining_days: number | null
  remark: string
  created_at: string
  /** 仅 reveal 后临时填充（明文密码不下发列表） */
  password?: string
}

export interface DeviceForm {
  device_name: string
  customer_id?: number | null
  device_type: string
  brand: string
  model: string
  serial_number: string
  ip_address: string
  port: number
  username: string
  password: string
  login_method: string
  location: string
  interface: string[]
  os_version: string
  rule_version: string
  is_maintenance: boolean
  is_in_use: boolean
  license_expiry: string
  license_start: string
  remark: string
}

export interface DeviceQuery {
  page?: number
  page_size?: number
  search?: string
  brand?: string
  model?: string
  device_type?: string
  customer_id?: number
}

export function fetchDevices(params: DeviceQuery) {
  return request<PageResult<Device>>({ url: '/api/devices', method: 'GET', params })
}

export function fetchDevice(id: number) {
  return request<Device>({ url: `/api/devices/${id}`, method: 'GET' })
}

export function createDevice(data: DeviceForm) {
  return request<{ id: number }>({ url: '/api/devices', method: 'POST', data })
}

export function updateDevice(id: number, data: DeviceForm) {
  return request<{ id: number }>({ url: `/api/devices/${id}`, method: 'PUT', data })
}

export function deleteDevice(id: number) {
  return request<null>({ url: `/api/devices/${id}`, method: 'DELETE' })
}

export function revealPassword(id: number) {
  return request<{ password: string }>({
    url: `/api/v2/devices/${id}/reveal-password`,
    method: 'POST',
  })
}
