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
      ElTooltip: { template: '<span><slot /></span>' },
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
    ? { notify_enabled: true, has_wecom_webhook: true, events: { ticket_new: '工单受理' }, bindings: [{ id: 3, name: '自定义服务群', channel_type: 'wecom', notify_enabled: true, has_wecom_webhook: true, subscriptions: {}, quiet_start: 0, quiet_end: 0, digest_minutes: 0 }] } : url.endsWith('/test') ? { queued: true } : { items: [] }))
  mocks.confirm.mockResolvedValue(true)
})

describe('客户通知设置', () => {
  it('新群默认匹配客户名称，可手动修改保存，切换客户重新匹配', async () => {
    mocks.request.mockImplementation(({ url }) => Promise.resolve(url.endsWith('notify-settings')
      ? { notify_enabled: false, has_wecom_webhook: false, events: {}, bindings: [] } : { items: [] }))
    const wrapper = mountDialog()
    await wrapper.vm.open(8, '吉安市水利局')
    const input = wrapper.findAllComponents({ name: 'ElInput' })[0]!
    expect(input.attributes('modelvalue')).toBe('吉安市水利局运维服务群')
    input.vm.$emit('update:modelValue', '吉安市水利局网络保障群')
    await flushPromises()
    await wrapper.findAll('button').find(b => b.text() === '保存')!.trigger('click')
    await flushPromises()
    expect(mocks.request).toHaveBeenCalledWith(expect.objectContaining({ method: 'PUT', data: expect.objectContaining({ name: '吉安市水利局网络保障群', create: true }) }))
    await wrapper.vm.open(9, '客户 B')
    expect(wrapper.findAllComponents({ name: 'ElInput' })[0]!.attributes('modelvalue')).toBe('客户 B运维服务群')
  })

  it('保留自定义名称，新增群使用默认名称，渠道与状态开关同组', async () => {
    const wrapper = mountDialog()
    await wrapper.vm.open(8, '吉安市水利局')
    expect(wrapper.findAllComponents({ name: 'ElInput' })[0]!.attributes('modelvalue')).toBe('自定义服务群')
    expect(wrapper.find('.notify-channel-row').findAllComponents({ name: 'ElSwitch' })).toHaveLength(1)
    expect(wrapper.find('.notify-channel-row').text()).toContain('已绑定')
    await wrapper.findAll('button').find(b => b.text() === '新增群')!.trigger('click')
    expect(wrapper.findAllComponents({ name: 'ElInput' })[0]!.attributes('modelvalue')).toBe('吉安市水利局运维服务群')
  })

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
