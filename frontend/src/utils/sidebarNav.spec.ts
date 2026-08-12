import { describe, it, expect } from 'vitest'
import { sidebarTarget, isRouteActive, toRouterPath } from '@/utils/sidebarNav'

describe('toRouterPath', () => {
  it('/app 前缀 → 内部路由路径（router-link 专用）', () => {
    expect(toRouterPath('/app/knowledge-base/5')).toBe('/knowledge-base/5')
    expect(toRouterPath('/app/tickets/12')).toBe('/tickets/12')
    expect(toRouterPath('/app/devices/3')).toBe('/devices/3')
    expect(toRouterPath('/app/')).toBe('/')
    expect(toRouterPath('/app')).toBe('/')
  })

  it('保留 query 参数', () => {
    expect(toRouterPath('/app/knowledge-base?category=故障处置')).toBe('/knowledge-base?category=故障处置')
    expect(toRouterPath('/app/spare-parts?tab=stocks')).toBe('/spare-parts?tab=stocks')
  })

  it('非 /app 路径原样返回', () => {
    expect(toRouterPath('/customers/1')).toBe('/customers/1')
    expect(toRouterPath('#')).toBe('#')
  })
})

describe('sidebarTarget', () => {
  it('已迁移路径 → SPA 跳转（原样路径）', () => {
    expect(sidebarTarget('/tickets')).toEqual({ mode: 'spa', path: '/tickets', query: '' })
    expect(sidebarTarget('/devices')).toEqual({ mode: 'spa', path: '/devices', query: '' })
    expect(sidebarTarget('/customers')).toEqual({ mode: 'spa', path: '/customers', query: '' })
  })

  it('保留 query（知识库分类链接）', () => {
    expect(sidebarTarget('/knowledge-base?category=故障处置')).toEqual({
      mode: 'spa', path: '/knowledge-base', query: '?category=故障处置',
    })
  })

  it('/app 前缀路径 → SPA 跳转（剥前缀）', () => {
    expect(sidebarTarget('/app/tickets')).toEqual({ mode: 'spa', path: '/tickets', query: '' })
    expect(sidebarTarget('/app/knowledge-base?category=技术手册')).toEqual({
      mode: 'spa', path: '/knowledge-base', query: '?category=技术手册',
    })
    expect(sidebarTarget('/app/')).toEqual({ mode: 'spa', path: '/', query: '' })
  })

  it('根路径 → SPA 工作台', () => {
    expect(sidebarTarget('/')).toEqual({ mode: 'spa', path: '/', query: '' })
  })

  it('未映射路径 → Vue 兜底路由，不回退整页加载', () => {
    expect(sidebarTarget('/users')).toEqual({
      mode: 'spa', path: '/__missing_sidebar_route__', query: '',
    })
    expect(sidebarTarget('/task-schedule/')).toEqual({ mode: 'spa', path: '/task-schedule', query: '' })
    expect(sidebarTarget('/tools/network')).toEqual({
      mode: 'spa', path: '/__missing_sidebar_route__', query: '',
    })
    // 后端映射后（/knowledge-base/add → /app/knowledge-base）会命中正常 SPA 路由
    expect(sidebarTarget('/knowledge-base/add')).toEqual({
      mode: 'spa', path: '/__missing_sidebar_route__', query: '',
    })
    expect(sidebarTarget('/app/knowledge-base')).toEqual({ mode: 'spa', path: '/knowledge-base', query: '' })
  })
})

describe('isRouteActive', () => {
  it('path 相同且无 query 时激活', () => {
    expect(isRouteActive('/devices', {}, '/app/devices')).toBe(true)
    expect(isRouteActive('/devices', {}, '/devices')).toBe(true)
    expect(isRouteActive('/tickets', {}, '/app/tickets')).toBe(true)
  })

  it('path 不同不激活', () => {
    expect(isRouteActive('/devices', {}, '/app/tickets')).toBe(false)
    expect(isRouteActive('/devices', { tab: 'types' }, '/app/device-dicts?tab=types')).toBe(false)
  })

  it('带 query 的链接：同 path 不同 query 只激活匹配项', () => {
    expect(isRouteActive('/device-dicts', { tab: 'brands' }, '/app/device-dicts?tab=types')).toBe(false)
    expect(isRouteActive('/device-dicts', { tab: 'types' }, '/app/device-dicts?tab=types')).toBe(true)
    expect(isRouteActive('/spare-parts', { tab: 'stocks' }, '/app/spare-parts?tab=stocks')).toBe(true)
    expect(isRouteActive('/spare-parts', { tab: 'purchases' }, '/app/spare-parts?tab=stocks')).toBe(false)
    expect(isRouteActive('/sales', { tab: 'quotations' }, '/app/sales?tab=opps')).toBe(false)
  })

  it('无 query 的链接：当前 route.query 非空时不激活', () => {
    expect(isRouteActive('/spare-parts', { tab: 'stocks' }, '/app/spare-parts')).toBe(false)
    expect(isRouteActive('/knowledge-base', { category: '技术手册' }, '/app/knowledge-base')).toBe(false)
    expect(isRouteActive('/spare-parts', {}, '/app/spare-parts')).toBe(true)
  })

  it('链接参数全部匹配才激活（路由允许多出无关参数）', () => {
    expect(isRouteActive('/spare-parts', { tab: 'stocks', search: 'x' }, '/app/spare-parts?tab=stocks')).toBe(true)
    expect(isRouteActive('/spare-parts', { tab: 'stocks' }, '/app/spare-parts?tab=stocks&search=x')).toBe(false)
  })

  it('中文 query 值按原样匹配', () => {
    expect(isRouteActive('/knowledge-base', { category: '故障处置' }, '/app/knowledge-base?category=故障处置')).toBe(true)
    expect(isRouteActive('/knowledge-base', { category: '技术手册' }, '/app/knowledge-base?category=故障处置')).toBe(false)
  })
})
