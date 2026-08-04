import request from '@/utils/request'

export interface DictItem {
  id: number
  name: string
  sort_order: number
  field_type?: string
}

type Resource = 'types' | 'brands' | 'network-types' | 'custom-fields'

export function fetchDeviceDict(resource: Resource) {
  return request<DictItem[]>({ url: `/api/device-dicts/${resource}`, method: 'GET' })
}

export function createDeviceDict(resource: Resource, payload: { name: string; sort_order: number; field_type?: string }) {
  return request<{ id: number }>({ url: `/api/device-dicts/${resource}`, method: 'POST', data: payload })
}

export function updateDeviceDict(resource: Resource, id: number, payload: { name: string; sort_order: number; field_type?: string }) {
  return request<null>({ url: `/api/device-dicts/${resource}/${id}`, method: 'PUT', data: payload })
}

export function deleteDeviceDict(resource: Resource, id: number) {
  return request<null>({ url: `/api/device-dicts/${resource}/${id}`, method: 'DELETE' })
}
