import request from '@/utils/request'
import type { CurrentUser } from '@/types'

export interface LoginPayload {
  username: string
  password: string
}

export interface LoginResult {
  user: CurrentUser
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
