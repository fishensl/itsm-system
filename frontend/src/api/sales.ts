import request from '@/utils/request'
import type { PageResult } from '@/types'

export interface Opportunity {
  id: number
  customer_id: number | null
  customer_name: string
  title: string
  stage: string
  expected_amount: number
  expected_close_date: string
  owner: string
  remark: string
  created_at: string
}

export interface Quotation {
  id: number
  number: string
  opportunity_id: number | null
  opportunity_title: string
  customer_id: number | null
  customer_name: string
  total_amount: number
  valid_until: string
  status: string
  created_at: string
}

export interface ContractItem {
  id: number
  number: string
  title: string
  customer_id: number | null
  customer_name: string
  opportunity_id: number | null
  amount: number
  status: string
  start_date: string
  end_date: string
  inspection_frequency: string
  task_template_id: number | null
  task_template_name: string
  auto_generate_tasks: boolean
  created_at: string
}

export interface ProjectItem {
  id: number
  name: string
  contract_id: number | null
  contract_title: string
  customer_id: number | null
  customer_name: string
  manager: string
  status: string
  start_date: string
  end_date: string
  progress: number
  budget: number
  created_at: string
}

export interface SalesDicts {
  opp_stages: string[]
  quotation_statuses: string[]
  contract_statuses: string[]
  project_statuses: string[]
  frequencies: string[]
  customers: { id: number; name: string }[]
  opportunities: { id: number; title: string }[]
  contracts: { id: number; title: string }[]
  templates: { id: number; name: string }[]
}

export interface PageQuery {
  page?: number
  page_size?: number
  search?: string
  status?: string
  stage?: string
  [key: string]: unknown
}

export const OPP_STAGE_TAG: Record<string, 'primary' | 'success' | 'warning' | 'danger' | 'info'> = {
  初步接触: 'primary',
  需求确认: 'primary',
  方案报价: 'primary',
  商务谈判: 'primary',
  成交: 'success',
  失败: 'danger',
}

export const QUOTATION_STATUS_TAG: Record<string, 'primary' | 'success' | 'warning' | 'danger' | 'info'> = {
  草稿: 'info',
  已发送: 'primary',
  已接受: 'success',
  已拒绝: 'danger',
}

export const CONTRACT_STATUS_TAG: Record<string, 'primary' | 'success' | 'warning' | 'danger' | 'info'> = {
  草签: 'info',
  已签: 'primary',
  执行中: 'success',
  已完成: 'warning',
  已终止: 'danger',
}

export const PROJECT_STATUS_TAG: Record<string, 'primary' | 'success' | 'warning' | 'danger' | 'info'> = {
  未启动: 'info',
  进行中: 'primary',
  已完成: 'success',
  已暂停: 'warning',
}

export function fetchOpportunities(params: PageQuery) {
  return request<PageResult<Opportunity>>({ url: '/api/opportunities', method: 'GET', params })
}

export function fetchOpportunity(id: number) {
  return request<Opportunity>({ url: `/api/opportunities/${id}`, method: 'GET' })
}

export function createOpportunity(data: Record<string, unknown>) {
  return request<{ id: number }>({ url: '/api/opportunities', method: 'POST', data })
}

export function updateOpportunity(id: number, data: Record<string, unknown>) {
  return request<{ id: number }>({ url: `/api/opportunities/${id}`, method: 'PUT', data })
}

export function deleteOpportunity(id: number) {
  return request<null>({ url: `/api/opportunities/${id}`, method: 'DELETE' })
}

export function fetchQuotations(params: PageQuery) {
  return request<PageResult<Quotation>>({ url: '/api/quotations', method: 'GET', params })
}

export function createQuotation(data: Record<string, unknown>) {
  return request<{ id: number }>({ url: '/api/quotations', method: 'POST', data })
}

export function updateQuotation(id: number, data: Record<string, unknown>) {
  return request<{ id: number }>({ url: `/api/quotations/${id}`, method: 'PUT', data })
}

export function deleteQuotation(id: number) {
  return request<null>({ url: `/api/quotations/${id}`, method: 'DELETE' })
}

export function fetchContracts(params: PageQuery) {
  return request<PageResult<ContractItem>>({ url: '/api/contracts', method: 'GET', params })
}

export function createContract(data: Record<string, unknown>) {
  return request<{ id: number; generated: number }>({ url: '/api/contracts', method: 'POST', data })
}

export function updateContract(id: number, data: Record<string, unknown>) {
  return request<{ id: number; generated: number }>({ url: `/api/contracts/${id}`, method: 'PUT', data })
}

export function deleteContract(id: number) {
  return request<null>({ url: `/api/contracts/${id}`, method: 'DELETE' })
}

export function fetchProjects(params: PageQuery) {
  return request<PageResult<ProjectItem>>({ url: '/api/projects', method: 'GET', params })
}

export function createProject(data: Record<string, unknown>) {
  return request<{ id: number }>({ url: '/api/projects', method: 'POST', data })
}

export function updateProject(id: number, data: Record<string, unknown>) {
  return request<{ id: number }>({ url: `/api/projects/${id}`, method: 'PUT', data })
}

export function deleteProject(id: number) {
  return request<null>({ url: `/api/projects/${id}`, method: 'DELETE' })
}

export function fetchSalesDicts() {
  return request<SalesDicts>({ url: '/api/dicts/sales', method: 'GET' })
}
