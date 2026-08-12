import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import * as authApi from '@/api/auth'
import type { CurrentUser, SidebarGroup } from '@/types'

export const useUserStore = defineStore('user', () => {
  const user = ref<CurrentUser | null>(null)
  const sidebarGroups = ref<SidebarGroup[]>([])
  const loaded = ref(false)
  const pendingMfa = ref<'verify' | 'bind' | null>(null)

  const isAuthenticated = computed(() => user.value !== null)
  const permissions = computed(() => user.value?.permissions || [])

  /** 权限判定（供 v-perm 指令与组件使用） */
  function hasPerm(code?: string): boolean {
    if (!code) return true
    if (!user.value) return false
    if (user.value.roles?.includes('admin')) return true
    if (user.value.role === 'admin') return true
    return permissions.value.includes(code)
  }

  /** 是否为部门负责人（后端 departments.head_id 推断） */
  const isSupervisor = computed(() => Boolean(user.value?.is_supervisor))

  async function init() {
    if (loaded.value) return
    try {
      user.value = await authApi.fetchMe()
      sidebarGroups.value = await authApi.fetchSidebarGroups()
    } catch {
      user.value = null
    } finally {
      loaded.value = true
    }
  }

  async function login(username: string, password: string) {
    const result = await authApi.login({ username, password })
    if (result.mfa_required || result.bind_required) {
      pendingMfa.value = result.bind_required ? 'bind' : 'verify'
      return result
    }
    if (!result.user) throw new Error('登录响应缺少用户信息')
    user.value = result.user
    pendingMfa.value = null
    loaded.value = true
    sidebarGroups.value = await authApi.fetchSidebarGroups()
    return result
  }

  async function verifyMfa(code: string, recovery = false) {
    const result = await authApi.verifyLoginMfa(code, recovery)
    user.value = result.user
    pendingMfa.value = null
    loaded.value = true
    sidebarGroups.value = await authApi.fetchSidebarGroups()
  }

  async function logout() {
    try {
      await authApi.logout()
    } catch {
      /* 忽略登出接口异常 */
    }
    user.value = null
    loaded.value = false
  }

  return { user, sidebarGroups, loaded, pendingMfa, isAuthenticated, permissions, hasPerm, isSupervisor,
    init, login, verifyMfa, logout }
})
