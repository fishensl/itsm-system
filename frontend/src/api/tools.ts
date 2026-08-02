import request from '@/utils/request'

export interface IpCalcResult {
  network: string
  broadcast: string
  first: string
  last: string
  hosts: number
  mask: string
  mask_bits: number
  cidr: string
}

export interface ConvertResult {
  result: string
  to_base: number
  binary: string
  octal: string
  decimal: string
  hex: string
}

export interface MacFormatResult {
  result: string
  plain: string
  colon: string
  dash: string
  dot: string
}

export function ipCalc(data: { ip?: string; mask?: string | number; cidr?: string }) {
  return request<IpCalcResult>({ url: '/api/tools/ip-calc', method: 'POST', data })
}

export function convertBase(data: { value: string; from_base: number; to_base: number }) {
  return request<ConvertResult>({ url: '/api/tools/convert', method: 'POST', data })
}

export function formatMac(data: { mac: string }) {
  return request<MacFormatResult>({ url: '/api/tools/mac-format', method: 'POST', data })
}
