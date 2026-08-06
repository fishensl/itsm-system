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
  certifications?: string[]
  created_at: string
}

export interface UserListData {
  users: UserItem[]
  departments: { id: number; name: string }[]
  roles: string[]
  total?: number
  page?: number
  page_size?: number
}

export function fetchUsers(params?: Record<string, unknown>) {
  return request<UserListData>({ url: '/api/users', method: 'GET', params })
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

export function resetUserPassword(id: number, newPassword: string) {
  return request<null>({
    url: `/api/users/${id}/password`,
    method: 'PUT',
    data: { new_password: newPassword },
  })
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

export interface SysInfo {
  os_name: string
  os_release: string
  os_version: string
  os_platform: string
  machine: string
  hostname: string
  python_version: string
  python_impl: string
}

export type ComponentVersions = Record<string, string>

export interface DbInfo {
  engine: string
  version: string
  path: string
  size_mb?: number
}

export interface Resources {
  available: boolean
  error?: string
  cpu_percent?: number
  cpu_count?: number
  cpu_count_physical?: number
  memory_percent?: number
  memory_total_gb?: number
  memory_used_gb?: number
  memory_available_gb?: number
  disk_percent?: number
  disk_total_gb?: number
  disk_used_gb?: number
  disk_free_gb?: number
  process_memory_mb?: number
  process_pid?: number
  boot_time?: string
  process_start?: string
}

export interface DeployInfo {
  sys_info: SysInfo
  components: ComponentVersions
  db_info: DbInfo
  resources: Resources
}

export interface RecentUser {
  name: string
  username: string
  role: string
}

export interface SystemOverview {
  stats: Record<string, number>
  recent_users: RecentUser[]
  version: string
  deploy: DeployInfo
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

export interface SidebarCustomGroup {
  key: string
  title: string
  enabled: boolean
}

export function fetchSidebarCustom() {
  return request<SidebarCustomGroup[]>({ url: '/api/system/sidebar', method: 'GET' })
}

export function saveSidebarCustom(groups: SidebarCustomGroup[]) {
  return request<null>({ url: '/api/system/sidebar', method: 'PUT', data: { groups } })
}

export function resetSidebarCustom() {
  return request<null>({ url: '/api/system/sidebar/reset', method: 'POST' })
}

export interface AiConfigItem {
  id: number
  provider: string
  api_endpoint: string
  has_api_key: boolean
  model_name: string
  max_tokens: number
  temperature: number
  inspection_prompt_template: string
  fault_prompt_template: string
  is_enabled: boolean
}

export function fetchAiConfigs() {
  return request<AiConfigItem[]>({ url: '/api/ai-config', method: 'GET' })
}

export function createAiConfig(data: Record<string, unknown>) {
  return request<{ id: number }>({ url: '/api/ai-config', method: 'POST', data })
}

export function updateAiConfig(id: number, data: Record<string, unknown>) {
  return request<null>({ url: `/api/ai-config/${id}`, method: 'PUT', data })
}

export function deleteAiConfig(id: number) {
  return request<null>({ url: `/api/ai-config/${id}`, method: 'DELETE' })
}

export function testAiConfig(id: number) {
  return request<{ success: boolean; message: string }>({ url: `/api/ai-config/${id}/test`, method: 'POST' })
}

export function fetchBackupStats() {
  return request<{ stats: Record<string, number>; file_size_mb: number }>({
    url: '/api/system/backup/stats',
    method: 'GET',
  })
}

export function exportBackup(payload: { config_only?: boolean; password?: string }) {
  return request<{ filename: string; content: string }>({
    url: '/api/system/backup/export',
    method: 'POST',
    data: payload,
  })
}

export function importBackup(formData: FormData) {
  return request<{ message: string }>({
    url: '/api/system/backup/import',
    method: 'POST',
    data: formData,
  })
}

export interface RoleItem {
  id: number
  code: string
  name: string
  description: string
  is_system: boolean
  is_active: boolean
  sort_order: number
  permissions: string[]
}

export interface RoleListData {
  perm_map: Array<{ code: string; label: string }>
  roles: RoleItem[]
}

export function fetchRoles() {
  return request<RoleListData>({ url: '/api/roles', method: 'GET' })
}

export function createRole(data: Record<string, unknown>) {
  return request<{ id: number }>({ url: '/api/roles', method: 'POST', data })
}

export function updateRole(id: number, data: Record<string, unknown>) {
  return request<null>({ url: `/api/roles/${id}`, method: 'PUT', data })
}

export function deleteRole(id: number) {
  return request<null>({ url: `/api/roles/${id}`, method: 'DELETE' })
}

export function saveRolePermissions(id: number, codes: string[]) {
  return request<null>({ url: `/api/roles/${id}/permissions`, method: 'PUT', data: { codes } })
}

export interface UserPermissionOverride {
  grant_type: string
  expire_at: string
  remark: string
}

export function fetchUserPermissions(uid: number) {
  return request<{
    user: { id: number; username: string; realname: string }
    perm_map: Array<{ code: string; label: string }>
    overrides: Record<string, UserPermissionOverride>
  }>({ url: `/api/users/${uid}/permissions`, method: 'GET' })
}

export function saveUserPermissions(uid: number, overrides: Record<string, UserPermissionOverride>) {
  return request<null>({ url: `/api/users/${uid}/permissions`, method: 'PUT', data: { overrides } })
}
