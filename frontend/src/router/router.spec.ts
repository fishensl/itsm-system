import { describe, expect, it } from 'vitest'
import router from '@/router'

describe('router fallback', () => {
  it('resolves unknown paths to the dedicated 404 route', () => {
    const route = router.resolve('/removed/legacy/bookmark')

    expect(route.name).toBe('not-found')
    expect(route.meta.title).toBe('页面未找到')
    expect(route.redirectedFrom).toBeUndefined()
  })

  it('uses view permissions for region and category page entry', () => {
    expect(router.resolve('/regions').meta.perm).toBe('region:view')
    expect(router.resolve('/customer-categories').meta.perm).toBe('category:view')
  })

  it('resolves the named task supplement route under the SPA base exactly once', () => {
    const route = router.resolve({
      name: 'task-schedule',
      query: { task_id: '12', action: 'supplement' },
    })

    expect(route.name).toBe('task-schedule')
    expect(route.fullPath).toBe('/task-schedule?task_id=12&action=supplement')
    expect(route.href).toBe('/app/task-schedule?task_id=12&action=supplement')
  })
})
