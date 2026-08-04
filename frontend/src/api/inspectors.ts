import request from '@/utils/request'

export interface InspectorItem {
  id: number
  user_id: number
  name: string
  username: string
  role: string
  department_id: number | null
  phone: string
  email: string
  is_active: boolean
  remark: string
}

export interface AvailableUser {
  id: number
  name: string
  username: string
  role: string
  department_id: number | null
}

export interface InspectorListData {
  inspectors: InspectorItem[]
  available_users: AvailableUser[]
}

/** 巡检人员列表 + 可勾选候选用户 */
export function fetchInspectors() {
  return request<InspectorListData>({ url: '/api/inspectors', method: 'GET' })
}

export function createInspector(payload: { user_id: number; remark?: string }) {
  return request<{ id: number }>({ url: '/api/inspectors', method: 'POST', data: payload })
}

export function updateInspector(id: number, payload: { is_active: boolean; remark: string }) {
  return request<null>({ url: `/api/inspectors/${id}`, method: 'PUT', data: payload })
}

export function deleteInspector(id: number) {
  return request<null>({ url: `/api/inspectors/${id}`, method: 'DELETE' })
}
