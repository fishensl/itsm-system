import { afterEach, expect, it, vi } from 'vitest'
import { downloadImportTemplate } from './importTemplate'

afterEach(() => { vi.restoreAllMocks(); vi.unstubAllGlobals(); vi.useRealTimers() })

it('shows network restriction without opening a login page or downloading HTML', async () => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
    ok: false, status: 403, redirected: false,
    headers: new Headers({ 'content-type': 'application/json' }),
    json: async () => ({ message: '该功能仅限内网/VPN 访问' }),
  }))
  const toast = vi.spyOn(window, 'dispatchEvent')
  const click = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {})
  await downloadImportTemplate('device')
  expect(click).not.toHaveBeenCalled()
  expect((toast.mock.calls[0][0] as CustomEvent).detail.message).toContain('仅限内网')
})

it('saves Excel using the server filename and releases its object URL', async () => {
  vi.useFakeTimers()
  const blob = new Blob(['xlsx'])
  const createObjectURL = vi.fn().mockReturnValue('blob:template')
  const revokeObjectURL = vi.fn()
  vi.stubGlobal('URL', { createObjectURL, revokeObjectURL })
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
    ok: true, status: 200, redirected: false,
    headers: new Headers({
      'content-type': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
      'content-disposition': `attachment; filename*=UTF-8''${encodeURIComponent('设备导入模板.xlsx')}`,
    }),
    blob: async () => blob,
  }))
  let filename = ''
  vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(function (this: HTMLAnchorElement) {
    filename = this.download
  })
  await downloadImportTemplate('device')
  expect(filename).toBe('设备导入模板.xlsx')
  expect(createObjectURL).toHaveBeenCalledWith(blob)
  vi.runAllTimers()
  expect(revokeObjectURL).toHaveBeenCalledWith('blob:template')
})

it('reports an expired login without saving the redirected login response', async () => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ redirected: true, status: 200 }))
  const toast = vi.spyOn(window, 'dispatchEvent')
  await downloadImportTemplate('device')
  expect((toast.mock.calls[0][0] as CustomEvent).detail.message).toContain('登录状态已失效')
})
