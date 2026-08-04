import request from '@/utils/request'

export interface ContractTaskItem {
  id: number
  title: string
  customer_name: string
  inspection_frequency: string
  auto_generate_tasks: boolean
  task_template_id: number | null
  end_date: string
}

export interface ContractTaskListData {
  contracts: ContractTaskItem[]
  all_contracts: { id: number; title: string; customer_name: string; inspection_frequency: string }[]
  templates: { id: number; name: string }[]
}

export function fetchContractTasks() {
  return request<ContractTaskListData>({ url: '/api/contract-tasks', method: 'GET' })
}

export function generateContractTasks(contractId: number, toDate?: string) {
  return request<{ count: number; tasks: unknown[] }>({
    url: '/api/contract-tasks/generate',
    method: 'POST',
    data: { contract_id: contractId, to_date: toDate || '' },
  })
}

export function previewContractTasks(contractId: number) {
  return request<{ count: number; tasks: unknown[] }>({
    url: `/api/contract-tasks/preview/${contractId}`,
    method: 'GET',
  })
}

export function fetchGeneratedTasks(contractId: number) {
  return request<Array<{ id: number; title: string; status: string; planned_start: string; planned_end: string }>>({
    url: `/api/contract-tasks/generated/${contractId}`,
    method: 'GET',
  })
}
