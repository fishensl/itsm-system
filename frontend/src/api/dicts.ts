import request from '@/utils/request'

export interface DeviceDicts {
  brands: string[]
  device_types: { name: string }[]
  customers: { id: number; name: string }[]
  installation_positions: string[]
  power_supplies: string[]
}

/** 设备页统一字典（筛选 + 安装位置/电源配置表单枚举） */
export function fetchDeviceDicts() {
  return request<DeviceDicts>({ url: '/api/dicts/devices', method: 'GET' })
}
