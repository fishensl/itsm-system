/** 构造带筛选参数的 URL（空值自动忽略） */
export function buildQueryUrl(base: string, params: Record<string, unknown>): string {
  const q = new URLSearchParams()
  Object.entries(params).forEach(([k, v]) => {
    if (v !== undefined && v !== null && v !== '') q.set(k, String(v))
  })
  const qs = q.toString()
  return qs ? `${base}?${qs}` : base
}
