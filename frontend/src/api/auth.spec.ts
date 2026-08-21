import { beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('@/utils/request', () => ({ default: vi.fn() }))

import request from '@/utils/request'
import { login, verifyLoginMfa } from '@/api/auth'

describe('authentication request redirect policy', () => {
  beforeEach(() => vi.mocked(request).mockReset())

  it('lets the password form handle its own 401 response', () => {
    login({ username: 'op', password: 'invalid' })
    expect(request).toHaveBeenCalledWith(expect.objectContaining({
      url: '/api/auth/login',
      skipAuthRedirect: true,
    }))
  })

  it('keeps an MFA error on the MFA form instead of reloading the password page', () => {
    verifyLoginMfa('000000')
    expect(request).toHaveBeenCalledWith(expect.objectContaining({
      url: '/api/auth/mfa/verify',
      skipAuthRedirect: true,
    }))
  })
})
