import request from '@/utils/request'

export type CredentialPurpose =
  | 'device.password.create'
  | 'device.password.update'
  | 'device.password.reveal'
  | 'device.password.import'
  | 'device.password.export_unlock'
  | 'backup.password.export'
  | 'backup.password.import'
  | 'ai.credential.create'
  | 'ai.credential.update'
  | 'notification.credential.update'

export interface CredentialChallenge {
  version: 1
  challenge_id: string
  kid: string
  server_public_key: JsonWebKey
  salt: string
  context_hash: string
  request_aad: string
  response_aad: string
  expires_at: string
}

export function issueCredentialChallenge(data: {
  version: 1
  purpose: CredentialPurpose
  target_id?: number | string
  history_id?: number
  client_public_key: JsonWebKey
}) {
  return request<CredentialChallenge>({
    url: '/api/security/credential-envelope/challenge',
    method: 'POST',
    data,
  })
}
