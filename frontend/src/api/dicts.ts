import request from '@/utils/request'

export interface DeviceDicts {
  brands: string[]
  device_types: { name: string }[]
  device_categories?: { key: string; label: string; description: string }[]
  network_types: string[]
  customers: { id: number; name: string }[]
  installation_positions: string[]
  power_supplies: string[]
  login_methods: string[]
  room_locations: string[]
}

/** 设备页统一字典；customer_id 用于将机房位置候选限制到当前客户。 */
export function fetchDeviceDicts(params?: { customer_id?: number }) {
  return request<DeviceDicts>({ url: '/api/dicts/devices', method: 'GET', params })
}
