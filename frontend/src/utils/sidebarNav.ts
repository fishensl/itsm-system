import router from '@/router'
import { toRouterPath } from '@/utils/appRoute'

export { toRouterPath }

/** 侧栏只允许 SPA 内跳转；旧路径由后端兼容映射，未知路径交给 Vue 兜底路由。 */
export type SidebarTarget = { mode: 'spa'; path: string; query: string }

/** 已注册的 SPA 页面路径集合（排除动态段路由与无 name 的兜底路由） */
const SPA_PATHS = new Set(
  router
    .getRoutes()
    .filter((r) => r.name && !r.path.includes(':'))
    .map((r) => r.path.replace(/\/+$/, '') || '/'),
)

/** 把菜单 URL 规范化为 Vue Router 目标，绝不回退整页服务端导航。 */
export function sidebarTarget(url: string): SidebarTarget {
  const qi = url.indexOf('?')
  const base = qi >= 0 ? url.slice(0, qi) : url
  const query = qi >= 0 ? url.slice(qi) : ''
  const path = (base.replace(/^\/app/, '').replace(/\/+$/, '')) || '/'
  return { mode: 'spa', path: SPA_PATHS.has(path) ? path : '/__missing_sidebar_route__', query }
}

/**
 * /app 前缀 URL → SPA 内部路由路径。
 * SPA 路由注册在 /app/ 历史基座下且不含 /app 前缀，router-link 直接使用
 * /app/... 会匹配不到路由 → 被兜底路由重定向回首页（如知识库标题/详情跳转）。
 */
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
