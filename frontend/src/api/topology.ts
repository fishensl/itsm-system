import request from '@/utils/request'
import type { PageResult } from '@/types'

export interface TopologyItem {
  id: number
  name: string
  customer_id: number | null
  customer_name: string
  type: string
  types: string[]
  file_count: number
  source: string
  upload_by: string
  has_thumbnail: boolean
  created_at: string
  updated_at: string
}

export interface TopologyFile {
  id: number
  file_type: string
  source: string
  file_path: string
  url: string
  thumbnail: string
  pdf: string
  vsdx: string
  svg: string
  upload_by: string
  created_at: string
}

export interface TopologyDetail {
  id: number
  name: string
  description: string
  customer_id: number | null
  customer_name: string
  region_id: number | null
  region_name: string
  source: string
  file_count: number
  files: TopologyFile[]
  has_editor: boolean
  editor_id: number
}

export interface TopologyForm {
  name: string
  description?: string
  customer_id?: number | null
  region_id?: number | null
  file_type?: string
  source?: string
}

export const TOPOLOGY_TYPE_TAG: Record<string, 'primary' | 'success' | 'warning' | 'danger' | 'info'> = {
  image: 'success',
  pdf: 'danger',
  visio: 'warning',
  drawio: 'primary',
  other: 'info',
}

export function fetchTopologies(params: Record<string, unknown>) {
  return request<PageResult<TopologyItem>>({ url: '/api/topologies', method: 'GET', params })
}

export function fetchTopology(id: number) {
  return request<TopologyDetail>({ url: `/api/topologies/${id}`, method: 'GET' })
}

export function createTopology(data: TopologyForm) {
  return request<{ id: number }>({ url: '/api/topologies', method: 'POST', data })
}

export function updateTopology(id: number, data: TopologyForm) {
  return request<null>({ url: `/api/topologies/${id}`, method: 'PUT', data })
}

export function deleteTopology(id: number) {
  return request<null>({ url: `/api/topologies/${id}`, method: 'DELETE' })
}

export interface TopologyDicts {
  customers: { id: number; name: string }[]
  regions: { id: number; name: string }[]
}

export function fetchTopologyDicts() {
  return request<TopologyDicts>({ url: '/api/topologies/dicts', method: 'GET' })
}

export function uploadTopology(formData: FormData) {
  return request<{ id: number }>({
    url: '/api/topologies/upload',
    method: 'POST',
    data: formData,
    headers: { 'Content-Type': 'multipart/form-data' },
  })
}
