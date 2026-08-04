import router from '@/router'

/**
 * 侧栏导航目标判定：SPA 内跳转 vs SSR 整页加载
 *
 * 侧栏数据源返回 SSR 原始路径（如 /tickets、/inspectors、/users）；
 * 已迁移到 Vue 的路由用 router-link 跳转，未迁移的保持 SSR 页面（整页加载）。
 */

export type SidebarTarget =
  | { mode: 'spa'; path: string; query: string }
  | { mode: 'ssr'; url: string }

/** 已注册的 SPA 页面路径集合（排除动态段路由与无 name 的兜底路由） */
const SPA_PATHS = new Set(
  router
    .getRoutes()
    .filter((r) => r.name && !r.path.includes(':'))
    .map((r) => r.path.replace(/\/+$/, '') || '/'),
)

/** 判定侧栏链接跳转方式 */
export function sidebarTarget(url: string): SidebarTarget {
  const qi = url.indexOf('?')
  const base = qi >= 0 ? url.slice(0, qi) : url
  const query = qi >= 0 ? url.slice(qi) : ''
  const path = (base.replace(/^\/app/, '').replace(/\/+$/, '')) || '/'
  if (SPA_PATHS.has(path)) {
    return { mode: 'spa', path, query }
  }
  return { mode: 'ssr', url }
}

/** 拆分链接为 path + query 参数（无 query 返回 null） */
function splitUrl(url: string): { path: string; params: URLSearchParams | null } {
  const qi = url.indexOf('?')
  const base = qi >= 0 ? url.slice(0, qi) : url
  const path = (base.replace(/^\/app/, '').replace(/\/+$/, '')) || '/'
  return { path, params: qi >= 0 ? new URLSearchParams(url.slice(qi + 1)) : null }
}

/**
 * 侧栏链接是否命中当前路由（path + query 全量匹配）
 *
 * - 有 query 的链接：链接含的每个参数都必须与当前 query 相等（允许路由多出无关参数）
 * - 无 query 的链接：要求当前 query 为空（访问 ?tab=stocks 时「备件档案」不高亮）
 */
export function isRouteActive(
  currentPath: string,
  currentQuery: Record<string, unknown>,
  url: string,
): boolean {
  const { path, params } = splitUrl(url)
  if (path !== currentPath) return false
  if (!params) return Object.keys(currentQuery).length === 0
  for (const [k, v] of params.entries()) {
    if (String(currentQuery[k] ?? '') !== v) return false
  }
  return true
}
