/** 把浏览器中的 /app 前缀地址转换为 Vue Router 内部路径。 */
export function toRouterPath(url: string): string {
  const path = url.replace(/^\/app(?=\/|[?#]|$)/, '')
  return path || '/'
}

/**
 * 登录后的站内回跳目标。
 *
 * redirect 可能来自浏览器完整 pathname，也可能来自 Vue Router；这里只接受
 * 站内绝对路径，并统一剥离 history base，避免 /app/app/... 命中 404。
 */
export function loginRedirectTarget(value: unknown): string {
  if (typeof value !== 'string' || !value.startsWith('/') || value.startsWith('//')) return '/'
  const target = toRouterPath(value)
  if (target === '/login' || target.startsWith('/login?') ||
      target === '/mfa' || target.startsWith('/mfa?')) return '/'
  return target
}
