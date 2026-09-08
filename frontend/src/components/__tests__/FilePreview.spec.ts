import { afterEach, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import FilePreview from '@/components/FilePreview.vue'

vi.mock('@/utils/request', () => ({
  requestProtectedBlob: vi.fn().mockRejectedValue(new Error('外网访问敏感文件或密码需要完成 MFA 登录验证')),
}))

afterEach(() => vi.unstubAllGlobals())

it('shows the MFA denial instead of silently leaving an empty preview', async () => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
    ok: false, redirected: false,
    headers: new Headers({ 'content-type': 'application/json' }),
    json: async () => ({ message: '外网访问敏感文件或密码需要完成 MFA 登录验证' }),
  }))
  const wrapper = mount(FilePreview, {
    props: { url: '/api/tickets/report/1', fileName: 'report.pdf' },
    global: { stubs: {
      'el-alert': { props: ['title'], template: '<div>{{ title }}</div>' },
      'el-empty': true,
    } },
  })
  await flushPromises()
  expect(wrapper.text()).toContain('MFA')
  expect(wrapper.find('iframe').exists()).toBe(false)
  wrapper.unmount()
})
