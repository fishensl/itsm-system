let token = ''
let expiresAt = 0
let pending: Promise<string> | null = null
let resolvePending: ((value: string) => void) | null = null
let rejectPending: ((reason?: unknown) => void) | null = null

export function currentOperationToken(): string {
  if (Date.now() >= expiresAt) {
    token = ''
    expiresAt = 0
  }
  return token
}

export function requestOperationToken(): Promise<string> {
  const existing = currentOperationToken()
  if (existing) return Promise.resolve(existing)
  if (pending) return pending
  pending = new Promise<string>((resolve, reject) => {
    resolvePending = resolve
    rejectPending = reject
  })
  window.dispatchEvent(new CustomEvent('itsm:op-verify-request'))
  return pending
}

export function completeOperationVerification(value: string, expiresIn: number) {
  token = value
  expiresAt = Date.now() + Math.max(1, expiresIn - 2) * 1000
  resolvePending?.(value)
  clearPending()
}

export function cancelOperationVerification() {
  rejectPending?.(new Error('已取消操作验证'))
  clearPending()
}

function clearPending() {
  pending = null
  resolvePending = null
  rejectPending = null
}
