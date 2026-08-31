import { afterEach, describe, expect, it, vi } from 'vitest'

import { isEnvelopeSupported, withCredentialEnvelope } from './credentialEnvelope'

vi.mock('@/api/security', () => ({
  getCredentialEnvelopeCapability: vi.fn(),
  issueCredentialChallenge: vi.fn(),
}))

import { getCredentialEnvelopeCapability } from '@/api/security'

const mockedCapability = vi.mocked(getCredentialEnvelopeCapability)

describe('credential envelope secure-context boundary', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('uses compatibility only when the server confirms the purpose is disabled', async () => {
    vi.stubGlobal('isSecureContext', false)
    mockedCapability.mockResolvedValue({ mode: 'off', enabled: false, required: false })
    const fallback = vi.fn(async () => 'raw')

    expect(isEnvelopeSupported()).toBe(false)
    await expect(withCredentialEnvelope({
      purpose: 'device.password.update',
      payload: { password: 'canary-secret' },
      execute: vi.fn(),
      fallback,
    })).resolves.toBe('raw')
    expect(fallback).toHaveBeenCalledOnce()
  })

  it('does not downgrade when the server enables the purpose', async () => {
    vi.stubGlobal('isSecureContext', false)
    mockedCapability.mockResolvedValue({ mode: 'optional', enabled: true, required: false })
    const fallback = vi.fn(async () => 'raw')

    await expect(withCredentialEnvelope({
      purpose: 'device.password.update',
      payload: { password: 'canary-secret' },
      execute: vi.fn(),
      fallback,
    })).rejects.toThrow('HTTPS')
    expect(fallback).not.toHaveBeenCalled()
  })
})
