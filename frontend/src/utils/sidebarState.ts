/** 侧栏展开分组持久化。 */

export const SIDEBAR_OPEN_KEY = 'sidebarOpenGroups'

export function loadOpenGroups(): string[] {
  try {
    const raw = sessionStorage.getItem(SIDEBAR_OPEN_KEY)
    if (raw) return JSON.parse(raw)
  } catch {
    /* sessionStorage 不可用/脏数据：忽略 */
  }
  return []
}

export function saveOpenGroups(keys: string[]) {
  try {
    sessionStorage.setItem(SIDEBAR_OPEN_KEY, JSON.stringify(keys))
  } catch {
    /* 忽略 */
  }
}

export function clearOpenGroups() {
  try {
    sessionStorage.removeItem(SIDEBAR_OPEN_KEY)
  } catch {
    /* 忽略 */
  }
}
