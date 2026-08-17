import { describe, it, expect, vi } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import { useUserStore } from '@/stores/user'
import * as authApi from '@/api/auth'

describe('user store', () => {
  it('hasPerm: admin 短路全量权限', () => {
    setActivePinia(createPinia())
    const store = useUserStore()
    store.user = {
      id: 1,
      username: 'admin',
      realname: '管理员',
      role: 'admin',
      department_id: null,
      region_ids: [],
      customer_ids: [],
      permissions: [],
    }
    expect(store.hasPerm('anything:xxx')).toBe(true)
    expect(store.hasPerm()).toBe(true)
  })

  it('hasPerm: 普通角色按权限码判定', () => {
    setActivePinia(createPinia())
    const store = useUserStore()
    store.user = {
      id: 2,
      username: 'viewer',
      realname: '查看者',
      role: 'viewer',
      department_id: null,
      region_ids: [],
      customer_ids: [],
      permissions: ['device:view', 'ticket:view'],
    }
    expect(store.hasPerm('device:view')).toBe(true)
    expect(store.hasPerm('device:edit')).toBe(false)
    expect(store.hasPerm(undefined)).toBe(true)
  })

  it('clearSession 只清理前端状态，不重复请求后端 logout', () => {
    setActivePinia(createPinia())
    const logoutSpy = vi.spyOn(authApi, 'logout')
    const store = useUserStore()
    store.user = {
      id: 1,
      username: 'admin',
      realname: '管理员',
      role: 'admin',
      department_id: null,
      region_ids: [],
      customer_ids: [],
      permissions: [],
    }
    store.sidebarGroups = [{ key: 'dashboard', title: '工作台', icon: 'HomeFilled',
      enabled: true, single_link: { name: '工作台', url: '/app/', icon: 'HomeFilled' }, children: [] }]
    store.loaded = true

    store.clearSession()

    expect(logoutSpy).not.toHaveBeenCalled()
    expect(store.user).toBeNull()
    expect(store.sidebarGroups).toEqual([])
    expect(store.loaded).toBe(false)
    logoutSpy.mockRestore()
  })
})

