import { describe, expect, it, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import CustomerNotifyDialog from '../CustomerNotifyDialog.vue'

const mocks = vi.hoisted(() => ({ request: vi.fn(), confirm: vi.fn(), envelope: vi.fn() }))
vi.mock('@/utils/request', () => ({ default: mocks.request }))
vi.mock('@/utils/credentialEnvelope', () => ({ withCredentialEnvelope: mocks.envelope }))
vi.mock('element-plus', () => ({ ElMessage: { info: vi.fn(), success: vi.fn() }, ElMessageBox: { confirm: mocks.confirm } }))

function mountDialog() {
  return mount(CustomerNotifyDialog, { global: {
    directives: { loading: () => {} },
    stubs: {
      ElDialog: { template: '<div><slot /><footer><slot name="footer" /></footer></div>' }, ElAlert: true,
      ElForm: { template: '<div><slot /></div>' }, ElFormItem: { template: '<div><slot /></div>' },
      ElButton: { props: ['disabled'], template: '<button :disabled="disabled"><slot /></button>' },
      ElInput: true, ElSwitch: true, ElTable: true, ElTableColumn: true, ElSelect: true, ElOption: true,
      ElCheckboxGroup: true, ElCheckbox: true, ElInputNumber: true,
    },
  } })
}

beforeEach(() => {
  vi.clearAllMocks()
  mocks.request.mockImplementation(({ url }) => Promise.resolve(url.endsWith('notify-settings')
    ? { notify_enabled: true, has_wecom_webhook: true, events: { ticket_new: '工单受理' }, bindings: [{ id: 3, name: '客户群', channel_type: 'wecom', notify_enabled: true, has_wecom_webhook: true, subscriptions: {}, quiet_start: 0, quiet_end: 0, digest_minutes: 0 }] } : url.endsWith('/test') ? { queued: true } : { items: [] }))
  mocks.confirm.mockResolvedValue(true)
})

describe('客户通知设置', () => {
  it('打开和保存配置不自动向真实群发送测试', async () => {
    const wrapper = mountDialog()
    await wrapper.vm.open(8, '客户 A')
    await flushPromises()
    expect(mocks.request.mock.calls.every(([c]) => !c.url.endsWith('/test'))).toBe(true)
    await wrapper.findAll('button').find(b => b.text() === '保存')!.trigger('click')
    await flushPromises()
    expect(mocks.request).toHaveBeenCalledWith(expect.objectContaining({ url: '/api/customers/8/notify-webhook', method: 'PUT', data: expect.objectContaining({ notify_enabled: true, binding_id: 3 }) }))
    expect(mocks.request.mock.calls.every(([c]) => !c.url.endsWith('/test'))).toBe(true)
  })

  it('修改静默配置后必须先保存才能测试', async () => {
    const wrapper = mountDialog()
    await wrapper.vm.open(8, '客户 A')
    const testButton = () => wrapper.findAll('button').find(b => b.text() === '发送测试')!
    expect(testButton().attributes('disabled')).toBeUndefined()
    wrapper.findAllComponents({ name: 'ElInputNumber' })[0]!.vm.$emit('update:modelValue', 22)
    await flushPromises()
    expect(testButton().attributes('disabled')).toBeDefined()
  })

  it('测试必须由操作者确认，并只使用已保存的客户目标', async () => {
    const wrapper = mountDialog()
    await wrapper.vm.open(8, '客户 A')
    await wrapper.findAll('button').find(b => b.text() === '发送测试')!.trigger('click')
    await flushPromises()
    expect(mocks.confirm).toHaveBeenCalledOnce()
    expect(mocks.request).toHaveBeenCalledWith({ url: '/api/customers/8/notify-webhook/test', method: 'POST', data: { binding_id: 3 } })
  })
})
