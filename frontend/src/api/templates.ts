import request from '@/utils/request'

// ==================== 任务模板 ====================
export interface TaskTemplateSection {
  key: string
  title: string
  enabled: boolean
}

export interface TaskTemplateItem {
  id: number
  name: string
  category: string
  inspection_type: string
  frequency: string
  customer_tier: string
  sections: TaskTemplateSection[]
  required_assets: Record<string, boolean>
  is_active: boolean
  remark: string
  device_template_ids: number[]
}

export interface DeviceTemplateRef {
  id: number
  name: string
  device_category: string
  device_sub_type: string
  items_count: number
}

export interface TaskTemplateListData {
  templates: TaskTemplateItem[]
  device_templates: DeviceTemplateRef[]
  customers: { id: number; name: string }[]
}

export function fetchTaskTemplates() {
  return request<TaskTemplateListData>({ url: '/api/task-templates', method: 'GET' })
}

export function createTaskTemplate(data: Record<string, unknown>) {
  return request<{ id: number }>({ url: '/api/task-templates', method: 'POST', data })
}

export function updateTaskTemplate(id: number, data: Record<string, unknown>) {
  return request<null>({ url: `/api/task-templates/${id}`, method: 'PUT', data })
}

export function deleteTaskTemplate(id: number) {
  return request<null>({ url: `/api/task-templates/${id}`, method: 'DELETE' })
}

export interface MatchGroup {
  device_category: string
  devices_count: number
  devices: Array<{ id: number; name: string; brand: string; model: string; ip: string; os_version: string }>
  matched_templates: Array<{ id: number; name: string; category: string; sub_type: string; items_count: number; match_score: number }>
}

export function matchDeviceTemplates(customerId: number) {
  return request<{ groups: MatchGroup[]; total_devices: number }>({
    url: `/api/task-templates/match/${customerId}`,
    method: 'GET',
  })
}

// ==================== 设备检查模板 ====================
export interface CheckItemField {
  label?: string
  field_type?: string
  required?: boolean
  allow_skip?: boolean
  skip_reasons?: string
  options?: string
  help_text?: string
  default_result?: string
  ping_target_default?: string
  min_version?: string
  min_rule_version?: string
  placeholder?: string
  sort_order?: number
}

export interface CheckItem {
  name: string
  description?: string
  enabled?: boolean
  required?: boolean
  allow_skip?: boolean
  field_type?: string
  options?: string
  help_text?: string
  default_result?: string
  ping_target_default?: string
  min_version?: string
  min_rule_version?: string
  sub_items?: CheckItemField[]
  sort_order?: number
}

export interface DeviceCheckTemplateItem {
  id: number
  name: string
  device_category: string
  device_sub_type: string
  items: CheckItem[]
  is_active: boolean
  remark: string
  total_sub_items: number
}

export interface DeviceCheckTemplateListData {
  groups: Record<string, DeviceCheckTemplateItem[]>
  category_order: string[]
}

export function fetchDeviceCheckTemplates() {
  return request<DeviceCheckTemplateListData>({ url: '/api/device-check-templates', method: 'GET' })
}

export function createDeviceCheckTemplate(data: Record<string, unknown>) {
  return request<{ id: number }>({ url: '/api/device-check-templates', method: 'POST', data })
}

export function updateDeviceCheckTemplate(id: number, data: Record<string, unknown>) {
  return request<null>({ url: `/api/device-check-templates/${id}`, method: 'PUT', data })
}

export function deleteDeviceCheckTemplate(id: number) {
  return request<null>({ url: `/api/device-check-templates/${id}`, method: 'DELETE' })
}
