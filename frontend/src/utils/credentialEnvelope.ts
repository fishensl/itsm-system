import {
  issueCredentialChallenge,
  type CredentialChallenge,
  type CredentialPurpose,
} from '@/api/security'

export interface CredentialEnvelope {
  version: 1
  challenge_id: string
  iv: string
  ciphertext: string
}

interface EnvelopeBinding {
  targetId?: number | string
  historyId?: number
}

interface EnvelopeContext {
  requestEnvelope: CredentialEnvelope
  decryptResponse<T>(envelope: CredentialEnvelope): Promise<T>
}

const encoder = new TextEncoder()
const decoder = new TextDecoder()

function fromBase64Url(value: string): Uint8Array {
  const normalized = value.replace(/-/g, '+').replace(/_/g, '/')
  const binary = atob(normalized + '='.repeat((4 - normalized.length % 4) % 4))
  return Uint8Array.from(binary, (char) => char.charCodeAt(0))
}

function toBase64Url(value: ArrayBuffer | Uint8Array): string {
  const bytes = value instanceof Uint8Array ? value : new Uint8Array(value)
  let binary = ''
  for (const byte of bytes) binary += String.fromCharCode(byte)
  return btoa(binary).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/g, '')
}

function concat(...parts: Uint8Array[]): Uint8Array {
  const output = new Uint8Array(parts.reduce((total, part) => total + part.length, 0))
  let offset = 0
  for (const part of parts) {
    output.set(part, offset)
    offset += part.length
  }
  return output
}

export function isEnvelopeSupported(): boolean {
  return Boolean(globalThis.isSecureContext && globalThis.crypto?.subtle)
}

async function deriveKey(
  privateKey: CryptoKey,
  challenge: CredentialChallenge,
  direction: 'c2s' | 's2c',
): Promise<CryptoKey> {
  const peer = await crypto.subtle.importKey(
    'jwk', challenge.server_public_key,
    { name: 'ECDH', namedCurve: 'P-256' }, false, [],
  )
  const shared = await crypto.subtle.deriveBits(
    { name: 'ECDH', public: peer }, privateKey, 256,
  )
  const hkdfKey = await crypto.subtle.importKey('raw', shared, 'HKDF', false, ['deriveKey'])
  const info = concat(
    encoder.encode(`itsm-credential-envelope/v1/${direction}/${challenge.challenge_id}/`),
    Uint8Array.from(challenge.context_hash.match(/.{2}/g) || [], (hex) => Number.parseInt(hex, 16)),
  )
  return crypto.subtle.deriveKey(
    { name: 'HKDF', hash: 'SHA-256', salt: fromBase64Url(challenge.salt), info },
    hkdfKey,
    { name: 'AES-GCM', length: 256 },
    false,
    direction === 'c2s' ? ['encrypt'] : ['decrypt'],
  )
}

async function prepareEnvelope(
  purpose: CredentialPurpose,
  binding: EnvelopeBinding,
  payload: Record<string, unknown>,
): Promise<EnvelopeContext> {
  if (!isEnvelopeSupported()) {
    throw new Error('当前浏览器环境不支持安全凭据传输，请通过 HTTPS 域名使用新版 Edge/Chrome')
  }
  const keyPair = await crypto.subtle.generateKey(
    { name: 'ECDH', namedCurve: 'P-256' }, false, ['deriveBits'],
  ) as CryptoKeyPair
  const clientPublicKey = await crypto.subtle.exportKey('jwk', keyPair.publicKey)
  const challenge = await issueCredentialChallenge({
    version: 1,
    purpose,
    target_id: binding.targetId,
    history_id: binding.historyId,
    client_public_key: clientPublicKey,
  })
  const [requestKey, responseKey] = await Promise.all([
    deriveKey(keyPair.privateKey, challenge, 'c2s'),
    deriveKey(keyPair.privateKey, challenge, 's2c'),
  ])
  const iv = crypto.getRandomValues(new Uint8Array(12))
  const ciphertext = await crypto.subtle.encrypt(
    { name: 'AES-GCM', iv, additionalData: fromBase64Url(challenge.request_aad), tagLength: 128 },
    requestKey,
    encoder.encode(JSON.stringify(payload)),
  )
  return {
    requestEnvelope: {
      version: 1,
      challenge_id: challenge.challenge_id,
      iv: toBase64Url(iv),
      ciphertext: toBase64Url(ciphertext),
    },
    async decryptResponse<T>(envelope: CredentialEnvelope): Promise<T> {
      if (envelope.challenge_id !== challenge.challenge_id || envelope.version !== 1) {
        throw new Error('敏感响应与本次操作不匹配')
      }
      const plaintext = await crypto.subtle.decrypt(
        {
          name: 'AES-GCM', iv: fromBase64Url(envelope.iv),
          additionalData: fromBase64Url(challenge.response_aad), tagLength: 128,
        },
        responseKey,
        fromBase64Url(envelope.ciphertext),
      )
      return JSON.parse(decoder.decode(plaintext)) as T
    },
  }
}

export async function withCredentialEnvelope<T>(options: {
  purpose: CredentialPurpose
  binding?: EnvelopeBinding
  payload: Record<string, unknown>
  execute: (context: EnvelopeContext) => Promise<T>
  fallback?: () => Promise<T>
}): Promise<T> {
  if (!isEnvelopeSupported()) {
    throw new Error('当前浏览器环境不支持安全凭据传输，请通过 HTTPS 域名使用新版 Edge/Chrome')
  }
  try {
    const context = await prepareEnvelope(
      options.purpose, options.binding || {}, options.payload)
    return await options.execute(context)
  } catch (error) {
    if (options.fallback && (error as Error).message === '凭据传输信封未启用') {
      return options.fallback()
    }
    throw error
  }
}

export async function withBinaryCredentialEnvelope<T>(options: {
  purpose: CredentialPurpose
  binding?: EnvelopeBinding
  plaintext: ArrayBuffer
  execute: (value: {
    challengeId: string
    iv: string
    ciphertext: Blob
  }) => Promise<T>
  fallback?: () => Promise<T>
}): Promise<T> {
  if (!isEnvelopeSupported()) {
    throw new Error('当前浏览器环境不支持安全凭据传输，请通过 HTTPS 域名使用新版 Edge/Chrome')
  }
  try {
    const keyPair = await crypto.subtle.generateKey(
      { name: 'ECDH', namedCurve: 'P-256' }, false, ['deriveBits'],
    ) as CryptoKeyPair
    const clientPublicKey = await crypto.subtle.exportKey('jwk', keyPair.publicKey)
    const challenge = await issueCredentialChallenge({
      version: 1,
      purpose: options.purpose,
      target_id: options.binding?.targetId,
      history_id: options.binding?.historyId,
      client_public_key: clientPublicKey,
    })
    const requestKey = await deriveKey(keyPair.privateKey, challenge, 'c2s')
    const iv = crypto.getRandomValues(new Uint8Array(12))
    const ciphertext = await crypto.subtle.encrypt(
      { name: 'AES-GCM', iv, additionalData: fromBase64Url(challenge.request_aad), tagLength: 128 },
      requestKey,
      options.plaintext,
    )
    return await options.execute({
      challengeId: challenge.challenge_id,
      iv: toBase64Url(iv),
      ciphertext: new Blob([ciphertext], { type: 'application/octet-stream' }),
    })
  } catch (error) {
    if (options.fallback && (error as Error).message === '凭据传输信封未启用') {
      return options.fallback()
    }
    throw error
  }
}
