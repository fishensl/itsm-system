import request from '@/utils/request'

export interface UserItem {
  id: number
  username: string
  realname: string
  role: string
  roles?: string[]
  role_name?: string
  department_id: number | null
  department_name: string
  is_active: boolean
  phone: string
  email: string
  certifications?: string[]
  region_ids?: number[]
  region_names?: string[]
  customer_ids?: number[]
  customer_names?: string[]
  notify_accounts?: Record<string, string>
  vpn_account?: string
  mfa_enabled?: boolean
  mfa_op_enabled?: boolean
  created_at: string
}

export interface UserListData {
  users: UserItem[]
  departments: { id: number; name: string }[]
  roles: string[]
  role_names?: Record<string, string>
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
  backup: Omit<BackupStatus, 'last_error'>
}

export function fetchSystemOverview() {
  return request<SystemOverview>({ url: '/api/system/overview', method: 'GET' })
}

export interface RepairDeviceCountsResult {
  fixed: number
  details: Array<{ customer_id: number; name: string; before: number; after: number }>
  total_customers: number
}

export function repairDeviceCounts() {
  return request<RepairDeviceCountsResult>({
    url: '/api/system/repair-device-counts',
    method: 'POST',
  })
}

export function fetchUiVersion() {
  return request<{ version: 'vue' | 'ssr'; vue_migrated_count: number }>({
    url: '/api/system/ui-version',
    method: 'GET',
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

export interface BackupStatus {
  enabled: boolean
  health: 'disabled' | 'never' | 'ok' | 'stale' | 'failed'
  last_attempt_at: string
  last_success_at: string
  last_failure_at: string
  last_error: string
  consecutive_failures: number
  last_duration_seconds: string
  rpo_age_hours: number | null
}

export function fetchBackupStats() {
  return request<{ stats: Record<string, number>; file_size_mb: number; backup: BackupStatus }>({
    url: '/api/system/backup/stats',
    method: 'GET',
  })
}

export function exportBackup(payload: { config_only?: boolean; password?: string }) {
  return request<{ token: string; filename: string; size: number }>({
    url: '/api/system/backup/export',
    method: 'POST',
    data: payload,
  })
}

export function importBackup(formData: FormData) {
  return request<{ message: string; pre_import_file?: string | null }>({
    url: '/api/system/backup/import',
    method: 'POST',
    data: formData,
  })
}

export interface BackupConfig {
  backup_enabled: string
  backup_time: string
  backup_keep: string
}

export function fetchBackupConfig() {
  return request<BackupConfig>({
    url: '/api/system/backup/config',
    method: 'GET',
  })
}

export function saveBackupConfig(payload: BackupConfig) {
  return request<null>({
    url: '/api/system/backup/config',
    method: 'POST',
    data: payload,
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
  user_count: number
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

// ==================== 设备密码导出审核（V24） ====================
export interface ExportReviewItem {
  id: number
  reason: string
  username: string
  realname: string
  created_at: string
}

export function fetchExportReviews() {
  return request<{ items: ExportReviewItem[] }>({
    url: '/api/v2/devices/export-password-reviews',
    method: 'GET',
  })
}

export function reviewExportRequest(id: number, action: 'approve' | 'reject', comment: string) {
  return request<null>({
    url: `/api/v2/devices/export-password-reviews/${id}`,
    method: 'POST',
    data: { action, comment },
  })
}

// ==================== 访问控制（V28：内网/VPN 可信网段） ====================
export interface AccessControlData {
  trusted_networks: string[]
  enabled: boolean
}

export function resetUserMfa(id: number, purpose: 'all' | 'login' | 'operation' = 'all') {
  return request<null>({ url: `/api/users/${id}/mfa-reset`, method: 'POST', data: { purpose } })
}

export function offboardUser(id: number) {
  return request<{ hook_warnings: string[] }>({
    url: `/api/users/${id}/offboard`, method: 'POST',
  })
}

export function fetchAccessControl() {
  return request<AccessControlData>({ url: '/api/system/access-control', method: 'GET' })
}

export function saveAccessControl(trusted_networks: string[]) {
  return request<AccessControlData>({
    url: '/api/system/access-control',
    method: 'PUT',
    data: { trusted_networks },
  })
}

// ==================== 多渠道通知（V28：渠道配置 + 通知规则） ====================
export interface NotifyChannelItem {
  id: number
  channel_type: string
  name: string
  is_enabled: boolean
  sort_order: number
  config: Record<string, unknown>
  has_secret: boolean
}

export function fetchNotifyChannels() {
  return request<{ channels: NotifyChannelItem[] }>({ url: '/api/notify/channels', method: 'GET' })
}

export function saveNotifyChannel(channel_type: string, data: Record<string, unknown>) {
  return request<NotifyChannelItem>({
    url: `/api/notify/channels/${channel_type}`,
    method: 'PUT',
    data,
  })
}

export function testNotifyChannel(channel_type: string, account: string, mode: string) {
  return request<{ ok: boolean; message: string }>({
    url: `/api/notify/channels/${channel_type}/test`,
    method: 'POST',
    data: { account, mode },
  })
}

export interface NotifyRuleItem {
  event_type: string
  label: string
  is_enabled: boolean
  roles: string[]
  users: number[]
}

export function fetchNotifyRules() {
  return request<{ rules: NotifyRuleItem[]; event_types: { key: string; label: string }[] }>({
    url: '/api/notify/rules',
    method: 'GET',
  })
}

export function saveNotifyRule(data: Record<string, unknown>) {
  return request<null>({ url: '/api/notify/rules', method: 'POST', data })
}
