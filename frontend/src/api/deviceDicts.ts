import request from '@/utils/request'

export interface DictItem {
  id: number
  name: string
  sort_order: number
  field_type?: string
  is_active?: boolean
}

export type Resource = 'types' | 'brands' | 'network-types' | 'power-configs' | 'custom-fields'

export function fetchDeviceDict(resource: Resource) {
  return request<DictItem[]>({ url: `/api/device-dicts/${resource}`, method: 'GET' })
}

export function createDeviceDict(resource: Resource, payload: { name: string; field_type?: string; is_active?: boolean }) {
  return request<{ id: number }>({ url: `/api/device-dicts/${resource}`, method: 'POST', data: payload })
}

export function updateDeviceDict(resource: Resource, id: number, payload: { name: string; field_type?: string; is_active?: boolean }) {
  return request<null>({ url: `/api/device-dicts/${resource}/${id}`, method: 'PUT', data: payload })
}

export function deleteDeviceDict(resource: Resource, id: number) {
  return request<null>({ url: `/api/device-dicts/${resource}/${id}`, method: 'DELETE' })
}

export function reorderDeviceDict(resource: Resource, ids: number[]) {
  return request<null>({ url: `/api/device-dicts/${resource}/reorder`, method: 'PUT', data: { ids } })
}
