import request from '@/utils/request'

export interface FirmwareItem {
  id: number
  brand: string
  model: string
  firmware_type: string
  version: string
  release_date: string
  changelog: string
  download_url: string
  file_size_mb: number
  md5_checksum: string
  is_latest: boolean
  min_compatible_hardware: string
  upgrade_guide: string
  remark: string
}

export interface FirmwareGroup {
  brand: string
  model: string
  types: Array<{ firmware_type: string; items: FirmwareItem[] }>
  devices: Array<{ id: number; name: string; os_version: string; rule_version: string }>
}

export interface FirmwareListData {
  groups: FirmwareGroup[]
  all_brands: string[]
  all_models: string[]
  all_types: string[]
}

export interface FirmwarePayload {
  brand: string
  model: string
  firmware_type: string
  version: string
  release_date?: string
  changelog?: string
  download_url?: string
  file_size_mb?: number
  md5_checksum?: string
  is_latest?: boolean
  min_compatible_hardware?: string
  upgrade_guide?: string
  remark?: string
}

export function fetchFirmwares(params: Record<string, string> = {}) {
  return request<FirmwareListData>({ url: '/api/firmwares', method: 'GET', params })
}

export function createFirmware(data: FirmwarePayload) {
  return request<{ id: number }>({ url: '/api/firmwares', method: 'POST', data })
}

export function updateFirmware(id: number, data: FirmwarePayload) {
  return request<null>({ url: `/api/firmwares/${id}`, method: 'PUT', data })
}

export function deleteFirmware(id: number) {
  return request<null>({ url: `/api/firmwares/${id}`, method: 'DELETE' })
}
