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

export interface RelatedTicket {
  id: number
  number: string
  title: string
  status: string
  created_at: string
}

export interface RelatedInspection {
  id: number
  title: string
  task_title: string
  overall_status: string
  review_status: string
  inspection_date: string
}

export function fetchDeviceRelated(id: number) {
  return request<{ tickets: RelatedTicket[]; inspections: RelatedInspection[] }>({
    url: `/api/devices/${id}/related`,
    method: 'GET',
  })
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

export function revealPassword(id: number, historyId?: number) {
  return request<{ password: string }>({
    url: `/api/v2/devices/${id}/reveal-password`,
    method: 'POST',
    data: historyId ? { history_id: historyId } : undefined,
  })
}

export interface PasswordHistoryItem {
  id: number
  changed_by: string
  created_at: string
  remark: string
}

export function fetchPasswordHistory(id: number) {
  return request<PasswordHistoryItem[]>({ url: `/api/v2/devices/${id}/password-history`, method: 'GET' })
}

export function exportDevices(params: { search?: string; customer_id?: number; with_password?: boolean }) {
  return request<{ filename: string; content: string }>({
    url: '/api/v2/devices/export',
    method: 'POST',
    data: params,
  })
}

export function importDevices(formData: FormData) {
  return request<{ created: number; errors: string[]; total_errors: number }>({
    url: '/api/v2/devices/import',
    method: 'POST',
    data: formData,
  })
}

export function createConfigBackup(deviceId: number, formData: FormData) {
  return request<{ id: number }>({ url: `/api/devices/${deviceId}/config-backup`, method: 'POST', data: formData })
}

export function deleteConfigBackup(id: number) {
  return request<null>({ url: `/api/devices/config-backup/${id}/delete`, method: 'POST' })
}

export function rollbackConfigBackup(id: number) {
  return request<{ id: number }>({ url: `/api/devices/config-backup/${id}/rollback`, method: 'POST' })
}

export interface DiffLine {
  tag: 'equal' | 'delete' | 'insert' | 'replace'
  line_a: string
  line_b: string
}

export function fetchConfigBackupDiff(a: number, b: number) {
  return request<{ lines: DiffLine[] }>({
    url: '/api/devices/config-backup/diff',
    method: 'GET',
    params: { a, b },
  })
}

// ==================== 配置备份（V22：巡检同步可见 + 受控下载/在线查看） ====================
export interface DeviceConfigBackup {
  id: number
  backup_type: string
  backup_method: string
  backup_date: string
  has_content: boolean
  has_file: boolean
  file_name: string
  checksum: string
  created_by: string
  created_at: string
}

export function fetchDeviceConfigBackups(deviceId: number) {
  return request<DeviceConfigBackup[]>({ url: `/api/devices/${deviceId}/config-backups`, method: 'GET' })
}

export function deviceConfigBackupDownloadUrl(backupId: number) {
  return `/api/devices/config-backup/${backupId}/download`
}

export function fetchDeviceConfigBackupContent(backupId: number) {
  return request<{ content: string }>({ url: `/api/devices/config-backup/${backupId}/content`, method: 'GET' })
}
