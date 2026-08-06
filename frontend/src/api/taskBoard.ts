import request from '@/utils/request'

export interface TaskBoardItem {
  id: number
  title: string
  status: string
  task_type: string
  customer_id: number | null
  customer_name: string
  planned_start: string
  planned_end: string
  assigned_to_user_id: number | null
  assigned_to_name: string
  estimated_effort: number | null
  actual_effort: number | null
  overdue: boolean
  priority: string
}

export interface TaskBoard {
  groups: Record<string, TaskBoardItem[]>
  status_tag: Record<string, string>
  total: number
  pending: number
  running: number
  reviewing: number
  done: number
  scope: 'all' | 'dept' | 'mine'
  scope_label: string
}

export interface TaskBoardQuery {
  customer_id?: number
  assignee_id?: number
  show_cancelled?: boolean
}

export function fetchTaskBoard(params: TaskBoardQuery) {
  return request<TaskBoard>({ url: '/api/task-board', method: 'GET', params })
}

export function setTaskStatus(id: number, status: string) {
  return request<null>({ url: `/api/task-board/${id}/status`, method: 'POST', data: { status } })
}

export interface TaskBoardDicts {
  customers: { id: number; name: string }[]
  assignees: { id: number; name: string }[]
}

export function fetchTaskBoardDicts() {
  return request<TaskBoardDicts>({ url: '/api/dicts/task-board', method: 'GET' })
}
