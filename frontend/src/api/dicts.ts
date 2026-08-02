import request from '@/utils/request'

export interface DeviceDicts {
  brands: string[]
  device_types: { name: string }[]
  customers: { id: number; name: string }[]
}

/** 设备列表页筛选字典（品牌/类型/客户） */
export function fetchDeviceDicts() {
  return request<DeviceDicts>({ url: '/api/dicts/devices', method: 'GET' })
}
