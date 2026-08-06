import { describe, it, expect } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import { useUserStore } from '@/stores/user'

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
})

