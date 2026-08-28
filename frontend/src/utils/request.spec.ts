import { describe, expect, it } from 'vitest'

import { apiErrorMessage } from './request'

describe('apiErrorMessage', () => {
  it('从后端统一错误契约中返回业务原因', () => {
    expect(apiErrorMessage({
      response: { data: { code: 1, message: 'Excel 缺少必需列「名称」' } },
    })).toBe('Excel 缺少必需列「名称」')
  })

  it('无后端业务消息时返回空字符串', () => {
    expect(apiErrorMessage(new Error('network error'))).toBe('')
  })
})
