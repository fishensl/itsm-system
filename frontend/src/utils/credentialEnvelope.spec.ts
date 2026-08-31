import { afterEach, describe, expect, it, vi } from 'vitest'

import { isEnvelopeSupported, withCredentialEnvelope } from './credentialEnvelope'

vi.mock('@/api/security', () => ({
  issueCredentialChallenge: vi.fn(),
}))

describe('credential envelope secure-context boundary', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('does not downgrade to raw credentials outside a secure context', async () => {
    vi.stubGlobal('isSecureContext', false)
    const fallback = vi.fn(async () => 'raw')

    expect(isEnvelopeSupported()).toBe(false)
    await expect(withCredentialEnvelope({
      purpose: 'device.password.update',
      payload: { password: 'canary-secret' },
      execute: vi.fn(),
      fallback,
    })).rejects.toThrow('HTTPS')
    expect(fallback).not.toHaveBeenCalled()
  })
})
