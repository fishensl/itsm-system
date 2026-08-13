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
})
