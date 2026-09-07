import { mount, flushPromises } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import ElementPlus from 'element-plus'
import MfaSetup from './mfaSetup.vue'

const mocks = vi.hoisted(() => ({ status: vi.fn(), setup: vi.fn(), toast: vi.fn() }))
vi.mock('@/api/auth', () => ({
  fetchMfaStatus: mocks.status, setupMfa: mocks.setup,
  confirmMfa: vi.fn(), rebindMfa: vi.fn(),
}))
vi.mock('@/stores/ui', () => ({ useUiStore: () => ({ toast: mocks.toast }) }))
vi.mock('@/stores/user', () => ({ useUserStore: () => ({ user: { mfa_enabled: true } }) }))

beforeEach(() => vi.clearAllMocks())

describe('修改密码中的身份验证器', () => {
  it('已绑定时只显示一份状态和紧凑换绑操作，保留原验证入口', async () => {
    mocks.status.mockResolvedValue({ account_enabled: true, binding_required: false })
    const wrapper = mount(MfaSetup, { props: { embedded: true }, global: { plugins: [ElementPlus] } })
    try {
      await flushPromises()
      expect(wrapper.find('.page-header').exists()).toBe(false)
      expect(wrapper.findAll('.el-tag')).toHaveLength(1)
      expect(wrapper.find('.el-result').exists()).toBe(false)
      expect(wrapper.find('.bind-card').classes()).toContain('summary-only')
      expect(wrapper.find('.binding-actions').text()).toContain('更换绑定')
      await wrapper.find('.binding-actions button').trigger('click')
      await flushPromises()
      expect(document.body.textContent).toContain('当前动态码或恢复码')
    } finally { wrapper.unmount() }
  })

  it('未绑定仍可扫码绑定，首次登录继续明确提示强制绑定', async () => {
    mocks.status.mockResolvedValue({ account_enabled: false, binding_required: true })
    mocks.setup.mockResolvedValue({ qr_data_uri: '', manual_secret: 'TEST-ONLY', backup_codes: [] })
    const wrapper = mount(MfaSetup, { global: { plugins: [ElementPlus] } })
    try {
      await flushPromises()
      expect(wrapper.text()).toContain('首次登录必须先绑定账号 MFA')
      await wrapper.find('.binding-actions button').trigger('click')
      await flushPromises()
      expect(mocks.setup).toHaveBeenCalledTimes(1)
      expect(wrapper.find('.bind-grid').exists()).toBe(true)
      expect(wrapper.text()).toContain('确认绑定')
    } finally { wrapper.unmount() }
  })
})
