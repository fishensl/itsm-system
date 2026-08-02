import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import * as authApi from '@/api/auth'
import type { CurrentUser, SidebarGroup } from '@/types'

export const useUserStore = defineStore('user', () => {
  const user = ref<CurrentUser | null>(null)
  const sidebarGroups = ref<SidebarGroup[]>([])
  const loaded = ref(false)

  const isAuthenticated = computed(() => user.value !== null)
  const permissions = computed(() => user.value?.permissions || [])

  /** 权限判定（供 v-perm 指令与组件使用） */
  function hasPerm(code?: string): boolean {
    if (!code) return true
    if (!user.value) return false
    if (user.value.role === 'admin') return true
    return permissions.value.includes(code)
  }

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
    user.value = result.user
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

  return { user, sidebarGroups, loaded, isAuthenticated, permissions, hasPerm, init, login, logout }
})
