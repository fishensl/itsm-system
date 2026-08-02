import request from '@/utils/request'
import type { PageResult } from '@/types'

export interface SparePart {
  id: number
  code: string
  name: string
  category: string
  brand: string
  model: string
  specification: string
  unit: string
  min_stock: number
  reference_price: number
  warranty_months: number
  manufacturer: string
  serial_number: string
  remark: string
  total_stock: number
  stock_alert: boolean
  stock_alert_label: string
  created_at: string
  stocks?: SpareStock[]
  purchases?: PurchaseOrderItem[]
  sales?: SalesOrderItem[]
}

export interface SpareStock {
  id: number
  spare_part_id: number
  spare_part_name: string
  location: string
  quantity: number
  unit_price: number
  updated_at: string
}

export interface PurchaseOrderItem {
  id: number
  number: string
  spare_part_id: number
  spare_part_name: string
  supplier_name: string
  quantity: number
  unit_price: number
  total: number
  purchase_date: string
  operator: string
  remark: string
  created_at: string
}

export interface SalesOrderItem {
  id: number
  number: string
  spare_part_id: number
  spare_part_name: string
  customer_id: number | null
  customer_name: string
  quantity: number
  unit_price: number
  total: number
  sales_date: string
  operator: string
  invoice_number: string
  remark: string
  created_at: string
}

export interface SpareDicts {
  spare_parts: { id: number; name: string }[]
  customers: { id: number; name: string }[]
  categories: string[]
}

export interface SparePartQuery {
  page?: number
  page_size?: number
  search?: string
  category?: string
}

export function fetchSpareParts(params: SparePartQuery) {
  return request<PageResult<SparePart>>({ url: '/api/spare-parts', method: 'GET', params })
}

export function fetchSparePart(id: number) {
  return request<SparePart>({ url: `/api/spare-parts/${id}`, method: 'GET' })
}

export function createSparePart(data: Record<string, unknown>) {
  return request<{ id: number }>({ url: '/api/spare-parts', method: 'POST', data })
}

export function updateSparePart(id: number, data: Record<string, unknown>) {
  return request<{ id: number }>({ url: `/api/spare-parts/${id}`, method: 'PUT', data })
}

export function deleteSparePart(id: number) {
  return request<null>({ url: `/api/spare-parts/${id}`, method: 'DELETE' })
}

export function fetchSpareStocks(params: Record<string, unknown>) {
  return request<PageResult<SpareStock>>({ url: '/api/spare-stocks', method: 'GET', params })
}

export function createSpareStock(data: Record<string, unknown>) {
  return request<{ id: number }>({ url: '/api/spare-stocks', method: 'POST', data })
}

export function updateSpareStock(id: number, data: Record<string, unknown>) {
  return request<{ id: number }>({ url: `/api/spare-stocks/${id}`, method: 'PUT', data })
}

export function deleteSpareStock(id: number) {
  return request<null>({ url: `/api/spare-stocks/${id}`, method: 'DELETE' })
}

export function fetchPurchaseOrders(params: Record<string, unknown>) {
  return request<PageResult<PurchaseOrderItem>>({ url: '/api/purchase-orders', method: 'GET', params })
}

export function createPurchaseOrder(data: Record<string, unknown>) {
  return request<{ id: number }>({ url: '/api/purchase-orders', method: 'POST', data })
}

export function deletePurchaseOrder(id: number) {
  return request<null>({ url: `/api/purchase-orders/${id}`, method: 'DELETE' })
}

export function fetchSalesOrders(params: Record<string, unknown>) {
  return request<PageResult<SalesOrderItem>>({ url: '/api/sales-orders', method: 'GET', params })
}

export function createSalesOrder(data: Record<string, unknown>) {
  return request<{ id: number }>({ url: '/api/sales-orders', method: 'POST', data })
}

export function deleteSalesOrder(id: number) {
  return request<null>({ url: `/api/sales-orders/${id}`, method: 'DELETE' })
}

export function fetchSpareDicts() {
  return request<SpareDicts>({ url: '/api/dicts/spare', method: 'GET' })
}
