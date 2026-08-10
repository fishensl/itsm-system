/** 统一 API 响应契约（与后端约定） */
export interface ApiResponse<T = unknown> {
  code: 0 | 1
  data: T
  message: string
}

export interface PageResult<T> {
  items: T[]
  total: number
  page: number
  page_size: number
}

export interface PageQuery {
  page?: number
  page_size?: number
  search?: string
  status?: string
  [key: string]: unknown
}

/** 当前登录用户信息 */
export interface CurrentUser {
  id: number
  username: string
  realname: string
  role: string
  roles?: string[]
  department_id: number | null
  region_ids: number[]
  customer_ids: number[]
  permissions: string[]
  /** 是否为部门负责人（部门主管，可执行派单等主管动作） */
  is_supervisor?: boolean
}

/** 侧栏分组（数据源与后端 sidebar_config 对齐） */
export interface SidebarChild {
  name: string
  url: string
  icon: string
  perm?: string
}

export interface SidebarGroup {
  key: string
  title: string
  icon: string
  enabled: boolean
  single_link?: { name: string; url: string; icon: string }
  children: SidebarChild[]
}
