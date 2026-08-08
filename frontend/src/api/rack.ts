import request from '@/utils/request'
import type { PageResult } from '@/types'

export interface RackItem {
  id: number
  customer_id: number | null
  customer_name: string
  name: string
  location?: string
  total_u: number
  used_u: number
  used_label: string
  used_pct: number
  usage_level: '低' | '中' | '高' | '已满'
  color: string
  pdu_total_w: number
  used_w: number
  remark: string
  install_count: number
}

export interface RackInstall {
  id: number
  rack_id: number
  device_id: number | null
  name: string
  brand: string
  model: string
  ip: string
  kind: '托管' | '手动'
  start_u: number
  occupy_u: number
  rated_w: number
  remark: string
}

export interface RackDetail extends RackItem {
  installs: RackInstall[]
}

export interface RackForm {
  name: string
  customer_id?: number | null
  location?: string
  total_u: number
  color: string
  pdu_total_w: number
  remark: string
}

export interface RackDevice {
  id: number
  name: string
  brand: string
  model: string
  ip: string
  installed: boolean
}

export interface InstallForm {
  rack_id?: number
  device_id?: number | null
  manual_name?: string
  manual_brand?: string
  manual_model?: string
  manual_ip?: string
  start_u: number
  occupy_u: number
  rated_w: number
  remark?: string
}

export interface RackDicts {
  customers: { id: number; name: string }[]
}

export const USAGE_LEVEL_TAG: Record<string, 'primary' | 'success' | 'warning' | 'danger' | 'info'> = {
  低: 'info',
  中: 'primary',
  高: 'warning',
  已满: 'danger',
}

export function fetchRacks(params: Record<string, unknown>) {
  return request<PageResult<RackItem>>({ url: '/api/v2/rack/cabinets', method: 'GET', params })
}

export function fetchRack(id: number) {
  return request<RackDetail>({ url: `/api/v2/rack/cabinets/${id}`, method: 'GET' })
}

export function createRack(data: RackForm) {
  return request<{ id: number }>({ url: '/api/v2/rack/cabinets', method: 'POST', data })
}

export function updateRack(id: number, data: RackForm) {
  return request<null>({ url: `/api/v2/rack/cabinets/${id}`, method: 'PUT', data })
}

export function deleteRack(id: number) {
  return request<null>({ url: `/api/v2/rack/cabinets/${id}`, method: 'DELETE' })
}

export function fetchRackDevices(params: { rack_id?: number; customer_id?: number }) {
  return request<{ items: RackDevice[] }>({ url: '/api/v2/rack/devices', method: 'GET', params })
}

export function createInstall(data: Record<string, unknown>) {
  return request<{ id: number }>({ url: '/api/v2/rack/installs', method: 'POST', data })
}

export function updateInstall(id: number, data: Record<string, unknown>) {
  return request<null>({ url: `/api/v2/rack/installs/${id}`, method: 'PUT', data })
}

export function deleteInstall(id: number) {
  return request<null>({ url: `/api/v2/rack/installs/${id}`, method: 'DELETE' })
}

export function fetchRackDicts() {
  return request<RackDicts>({ url: '/api/dicts/rack', method: 'GET' })
}

export interface RackTreeCustomer {
  id: number | null
  name: string
  racks: { id: number; name: string; total_u: number; color: string; install_count: number }[]
}

export interface RackTreeCity {
  city: string
  customers: RackTreeCustomer[]
}

export function fetchRackTree() {
  return request<RackTreeCity[]>({ url: '/api/v2/rack/tree', method: 'GET' })
}
