import request from '@/utils/request'
import type { CurrentUser } from '@/types'

export interface LoginPayload {
  username: string
  password: string
}

export interface LoginResult {
  user?: CurrentUser
  mfa_required?: boolean
  bind_required?: boolean
}

/** 登录（session cookie 由浏览器维护） */
export function login(payload: LoginPayload) {
  return request<LoginResult>({
    url: '/api/auth/login',
    method: 'POST',
    data: payload,
  })
}

export function logout() {
  return request<null>({ url: '/api/auth/logout', method: 'POST' })
}

/** 当前用户信息 + 权限码数组（路由守卫 / v-perm 数据源） */
export function fetchMe() {
  return request<CurrentUser>({ url: '/api/auth/me', method: 'GET' })
}

/** 侧栏分组（复用后端 sidebar_config，按权限过滤） */
export function fetchSidebarGroups() {
  return request<import('@/types').SidebarGroup[]>({
    url: '/api/auth/sidebar-groups',
    method: 'GET',
  })
}

/** 自助修改密码（成功后强制登出） */
export function changePassword(oldPassword: string, newPassword: string) {
  return request<null>({
    url: '/api/auth/change-password',
    method: 'POST',
    data: { old_password: oldPassword, new_password: newPassword },
  })
}

export function verifyLoginMfa(code: string, recovery = false) {
  return request<{ user: CurrentUser }>({
    url: '/api/auth/mfa/verify', method: 'POST', data: { code, recovery },
  })
}

export type MfaPurpose = 'login' | 'operation'

export interface MfaSetupResult {
  purpose: MfaPurpose
  manual_secret: string
  provisioning_uri: string
  qr_data_uri: string
  backup_codes: string[]
}

export function fetchMfaStatus() {
  return request<{ login_enabled: boolean; operation_enabled: boolean; backup_codes_remaining: number;
    mfa_enforce: boolean; op_code_enforce: boolean }>({ url: '/api/auth/mfa/status', method: 'GET' })
}

export function setupMfa(purpose: MfaPurpose) {
  return request<MfaSetupResult>({ url: '/api/auth/mfa/setup', method: 'POST', data: { purpose } })
}

export function confirmMfa(purpose: MfaPurpose, code: string) {
  return request<{ user: CurrentUser } | null>({
    url: '/api/auth/mfa/confirm', method: 'POST', data: { purpose, code },
  })
}

export function verifyOperationCode(code: string) {
  return request<{ token: string; expires_in: number }>({
    url: '/api/auth/op-verify', method: 'POST', data: { code },
  })
}

export function fetchSystemSecurityProfile() {
  return request<Record<string, string>>({ url: '/api/system/security-profile', method: 'GET' })
}

export function updateSystemSecurityProfile(data: Record<string, unknown>) {
  return request<Record<string, string>>({ url: '/api/system/security-profile', method: 'PUT', data })
}

// ==================== Dashboard ====================
export interface DashboardData {
  counts: Record<string, number>
  metrics: Array<{ label: string; value: number; sub: string; icon: string; accent: string; url?: string }>
  quick_entries: Array<{ url: string; title: string; sub: string; icon: string }>
  my_tasks: Array<{ type_label: string; type_color: string; title: string; sub: string; url: string; time: string }>
  expiring_devices: Array<{ id: number; device_name: string; customer_name: string; license_expiry: string; remaining_days: number }>
  expiring_customers: Array<{ id: number; name: string; contract_end_date: string; remaining_days: number | null }>
  recent_inspections: Array<{ id: number; title: string; customer_name: string; inspection_date: string; overall_status: string }>
  device_type_stats: Array<[string, number]>
}

export function fetchDashboard() {
  return request<DashboardData>({ url: '/api/dashboard/overview', method: 'GET' })
}
