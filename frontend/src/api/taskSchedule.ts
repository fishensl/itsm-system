import request from '@/utils/request'

export interface TaskScheduleItem {
  id: number
  title: string
  status: string
  priority: string
  task_type: string
  customer_id: number
  customer_name: string
  assignee_id: number | null
  assignee_name: string
  planned_start: string
  planned_end: string
  estimated_effort: number | null
  actual_effort: number | null
  overdue: boolean
  source: string
  remark: string
  contract_exception_status: string
  contract_exception_reason: string
  contract_exception_by: string
  contract_exception_at: string
}

export interface TaskScheduleData {
  tasks: TaskScheduleItem[]
  status_groups?: Record<string, TaskScheduleItem[]>
  engineer_groups?: Record<string, TaskScheduleItem[]>
  engineers: Array<{ id: number; name: string }>
  customers: Array<{ id: number; name: string }>
  kpi: {
    total: number
    pending: number
    running: number
    reviewing: number
    done: number
    contract_review: number
    overdue: number
    est_effort: number
    act_effort: number
  }
  view: string
}

export interface TaskScheduleQuery {
  view?: string
  period?: string
  start_from?: string
  start_to?: string
  q?: string
  overdue?: string
  customer_id?: number
  engineer_id?: number
}

export function fetchTaskSchedule(params: TaskScheduleQuery) {
  return request<TaskScheduleData>({ url: '/api/task-schedule', method: 'GET', params })
}

export function createTaskSchedule(data: Record<string, unknown>) {
  return request<{ id: number }>({ url: '/api/task-schedule', method: 'POST', data })
}

export function updateTaskSchedule(id: number, data: Record<string, unknown>) {
  return request<null>({ url: `/api/task-schedule/${id}`, method: 'PUT', data })
}

export function deleteTaskSchedule(id: number) {
  return request<null>({ url: `/api/task-schedule/${id}`, method: 'DELETE' })
}

export function reviewTaskContract(id: number, approved: boolean, comment = '') {
  return request<{ id: number; status: string; contract_exception_status: string }>({
    url: `/api/task-schedule/${id}/contract-review`,
    method: 'POST',
    data: { approved, comment },
  })
}

export function batchTaskSchedule(ids: number[], action: 'status' | 'assign' | 'delete', value?: unknown) {
  return request<{ count: number }>({
    url: '/api/task-schedule/batch',
    method: 'POST',
    data: { ids, action, value },
  })
}

export function fetchImportTemplate() {
  return request<{ filename: string; content: string }>({ url: '/api/task-schedule/import-template', method: 'GET' })
}

export function importTaskSchedule(formData: FormData) {
  return request<{ message: string }>({
    url: '/api/task-schedule/import',
    method: 'POST',
    data: formData,
  })
}

export interface RequiredAssets {
  report: boolean
  config_zip: boolean
  config_text: boolean
  topology: boolean
  asset_list: boolean
}

export interface RequiredAssetsData {
  required_assets: RequiredAssets
  devices: Array<{ id: number; device_name: string; device_type: string }>
}

export function fetchRequiredAssets(id: number) {
  return request<RequiredAssetsData>({ url: `/api/task-schedule/${id}/required-assets`, method: 'GET' })
}

/** 下载后端返回的 base64 文件（UTF-8 文件名安全解码） */
export function downloadBase64(b64: string, filename: string) {
  const bin = atob(b64)
  const bytes = new Uint8Array(bin.length)
  for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i)
  const blob = new Blob([bytes], {
    type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
  })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = decodeURIComponent(filename)
  a.click()
  URL.revokeObjectURL(url)
}
