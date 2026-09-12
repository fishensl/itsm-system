import { describe, expect, it, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import Notifications from './notifications.vue'

const mocks = vi.hoisted(() => ({ request: vi.fn(), prompt: vi.fn() }))
vi.mock('@/utils/request', () => ({ default: mocks.request }))
vi.mock('element-plus', () => ({ ElMessageBox: { prompt: mocks.prompt } }))

describe('客户服务信息', () => {
  it('展示最终信息无需验收，只在主动操作时提交可选反馈', async () => {
    mocks.request.mockResolvedValue({ items: [{ id: 'event1', title: '示例客户2026年第三季度巡检', customer_id: 1,
      event: 'inspection_approved', content: '任务状态：已完成\n累计人天：0.94 人天', created_at: '2026-09-12T00:00:00Z' }] })
    mocks.prompt.mockResolvedValue({ value: '收到，谢谢' })
    const wrapper = mount(Notifications, { global: { stubs: {
      ElButton: { template: '<button><slot /></button>' },
      ElCard: { template: '<div><slot /></div>' }, ElTag: true,
    } } })
    await flushPromises()
    expect(wrapper.text()).toContain('示例客户2026年第三季度巡检')
    expect(wrapper.text()).not.toContain('验收')
    expect(wrapper.text()).not.toContain('审核通过')
    expect(mocks.request.mock.calls.every(([c]) => !c.method)).toBe(true)
    await wrapper.findAll('button').find(b => b.text() === '反馈（可选）')!.trigger('click')
    await flushPromises()
    expect(mocks.request).toHaveBeenCalledWith({ url: '/api/customer-notifications/event1/confirm', method: 'POST', data: { feedback: '收到，谢谢' } })
    expect(mocks.request.mock.calls.every(([c]) => !c.url.startsWith('/api/tickets') && !c.url.startsWith('/api/task-schedule'))).toBe(true)
  })
})
