import request from '@/utils/request'

export interface UserItem {
  id: number
  username: string
  realname: string
  role: string
  department_id: number | null
  department_name: string
  is_active: boolean
  phone: string
  email: string
  created_at: string
}

export interface UserListData {
  users: UserItem[]
  departments: { id: number; name: string }[]
  roles: string[]
}

export function fetchUsers() {
  return request<UserListData>({ url: '/api/users', method: 'GET' })
}

export function createUser(data: Record<string, unknown>) {
  return request<{ id: number }>({ url: '/api/users', method: 'POST', data })
}

export function updateUser(id: number, data: Record<string, unknown>) {
  return request<null>({ url: `/api/users/${id}`, method: 'PUT', data })
}

export function deleteUser(id: number) {
  return request<null>({ url: `/api/users/${id}`, method: 'DELETE' })
}

export interface AuditItem {
  id: number
  username: string
  action: string
  target_type: string
  target_id: number | null
  detail: string
  ip: string
  created_at: string
}

export function fetchAuditLogs(params: Record<string, unknown>) {
  return request<{ items: AuditItem[]; total: number; page: number; page_size: number }>({
    url: '/api/audit-logs',
    method: 'GET',
    params,
  })
}

export function fetchAuditDicts() {
  return request<{ actions: string[]; target_types: string[] }>({
    url: '/api/dicts/audit',
    method: 'GET',
  })
}

export interface SystemOverview {
  stats: Record<string, number>
  version: string
}

export function fetchSystemOverview() {
  return request<SystemOverview>({ url: '/api/system/overview', method: 'GET' })
}

export function fetchUiVersion() {
  return request<{ version: 'vue' | 'ssr'; vue_migrated_count: number }>({
    url: '/api/system/ui-version',
    method: 'GET',
  })
}

export function setUiVersion(version: 'vue' | 'ssr') {
  return request<{ version: 'vue' | 'ssr' }>({
    url: '/api/system/ui-version',
    method: 'PUT',
    data: { version },
  })
}

export interface DepartmentItem {
  id: number
  name: string
  parent_id: number | null
  head_id: number | null
  sort_order: number
}

export function fetchDepartments() {
  return request<{ departments: DepartmentItem[]; users: { id: number; name: string }[] }>({
    url: '/api/departments',
    method: 'GET',
  })
}

export function createDepartment(data: Record<string, unknown>) {
  return request<{ id: number }>({ url: '/api/departments', method: 'POST', data })
}

export function updateDepartment(id: number, data: Record<string, unknown>) {
  return request<null>({ url: `/api/departments/${id}`, method: 'PUT', data })
}

export function deleteDepartment(id: number) {
  return request<null>({ url: `/api/departments/${id}`, method: 'DELETE' })
}
