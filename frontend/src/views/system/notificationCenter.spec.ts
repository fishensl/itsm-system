import { describe, expect, it, vi } from 'vitest'
import { shallowMount, flushPromises } from '@vue/test-utils'
import NotificationCenter from './notificationCenter.vue'

vi.mock('@/stores/user', () => ({ useUserStore: () => ({ hasPerm: () => false }) }))
vi.mock('@/api/meta', () => ({ fetchEntityMeta: async () => ({ profiles: { list: [] } }) }))
vi.mock('@/utils/request', () => ({ default: async ({ url }: { url: string }) => url === '/api/notify-center'
  ? { items: [], total: 0, metrics: { counts: {}, worker_healthy: true } } : {} }))

describe('通知中心刷新', () => {
  it('更新投递统计不改变查询对象，避免触发表格连续请求；筛选仍能生效', async () => {
    const wrapper = shallowMount(NotificationCenter, { global: { stubs: Object.fromEntries([
      'ElAlert', 'ElOption', 'ElSelect', 'ElButton', 'ElCollapseItem', 'ElCollapse', 'ElDivider',
      'ElCheckbox', 'ElInputNumber', 'ElInput', 'ElTableColumn', 'ElTable', 'ElDialog',
    ].map(name => [name, { name, template: '<div><slot /></div>' }])) } })
    await flushPromises()
    const table = wrapper.findComponent({ name: 'DataTable' })
    const initial = table.props('query')
    await table.props('fetchData')({ page: 1 })
    await flushPromises()
    expect(table.props('query')).toBe(initial)
    wrapper.findAllComponents({ name: 'ElSelect' })[0]!.vm.$emit('update:modelValue', 'failed')
    await flushPromises()
    expect(table.props('query')).not.toBe(initial)
    expect(table.props('query')).toEqual({ status: 'failed' })
    wrapper.unmount()
  })
})
