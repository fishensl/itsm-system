import request from '@/utils/request'

export interface RegionItem {
  id: number
  name: string
  parent_id: number | null
  sort_order: number
  children?: RegionItem[]
}

export interface CategoryItem {
  id: number
  name: string
  sort_order: number
}

export function fetchRegions() {
  return request<RegionItem[]>({ url: '/api/regions', method: 'GET' })
}

export function createRegion(payload: { name: string; parent_id?: number | null }) {
  return request<{ id: number }>({ url: '/api/regions', method: 'POST', data: payload })
}

export function updateRegion(id: number, payload: { name: string; parent_id?: number | null; sort_order: number }) {
  return request<null>({ url: `/api/regions/${id}`, method: 'PUT', data: payload })
}

export function deleteRegion(id: number) {
  return request<null>({ url: `/api/regions/${id}`, method: 'DELETE' })
}

export function fetchCategories() {
  return request<CategoryItem[]>({ url: '/api/customer-categories', method: 'GET' })
}

export function createCategory(payload: { name: string; sort_order: number }) {
  return request<{ id: number }>({ url: '/api/customer-categories', method: 'POST', data: payload })
}

export function updateCategory(id: number, payload: { name: string; sort_order: number }) {
  return request<null>({ url: `/api/customer-categories/${id}`, method: 'PUT', data: payload })
}

export function deleteCategory(id: number) {
  return request<null>({ url: `/api/customer-categories/${id}`, method: 'DELETE' })
}
