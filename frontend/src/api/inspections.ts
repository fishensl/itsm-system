import request from '@/utils/request'
import { buildQueryUrl } from '@/utils/queryUrl'
import type { PageResult } from '@/types'

export interface SubmissionAsset {
  id: number
  asset_type: string
  file_path: string
  file_name: string
  device_id: number | null
  device_name: string
  has_content: boolean
  content_text: string
  target_id: number | null
  skip_reason: string
}

export interface SubmissionVersion {
  id: number
  version_no: number
  report_file: boolean
  report_name: string
  content: Record<string, unknown>
  submitted_by_name: string
  submitted_at: string
  review_status: string
  reviewed_by_name: string
  reviewed_at: string
  review_comment: string
  revision_requirements: string
  checklist: Record<string, string>
  assets: SubmissionAsset[]
}

export interface Inspection {
  id: number
  title: string
  customer_id: number | null
  customer_name: string
  task_id: number | null
  task_title: string
  inspection_date: string
  overall_status: string
  review_status: string
  inspector_name: string
  inspector_user_id: number | null
  report_file: boolean
  report_label: string
  report_file_name: string
  submitted_report: boolean
  submitted_report_name: string
  complete: boolean
  missing_fields: string[]
  location: string
  conclusion: string
  content_json: unknown[]
  field_values_json: Record<string, unknown>
  sections_json: Record<string, unknown>
  review_comment: string
  reviewed_at: string
  created_at: string
}

export interface InspectionQuery {
  page?: number
  page_size?: number
  search?: string
  status?: string
  review_status?: string
  customer_id?: number
  task_id?: number
  date_from?: string
  date_to?: string
  incomplete_only?: number
}

export { OVERALL_STATUS_TAG, REVIEW_STATUS_TAG } from '@/utils/status'

export function fetchInspections(params: InspectionQuery) {
  return request<PageResult<Inspection>>({ url: '/api/inspections', method: 'GET', params })
}

export function fetchInspection(id: number) {
  return request<Inspection>({ url: `/api/inspections/${id}`, method: 'GET' })
}

export function createInspection(data: Record<string, unknown>) {
  return request<{ id: number }>({ url: '/api/inspections', method: 'POST', data })
}

export function updateInspection(id: number, data: Record<string, unknown>) {
  return request<{ id: number }>({ url: `/api/inspections/${id}`, method: 'PUT', data })
}

export function deleteInspection(id: number) {
  return request<null>({ url: `/api/inspections/${id}`, method: 'DELETE' })
}

export function submitInspection(id: number, formData?: FormData) {
  return request<null>({
    url: `/api/inspections/${id}/submit`,
    method: 'POST',
    data: formData,
  })
}

export function reviewInspection(id: number, approved: boolean, remark?: string, requirements?: string, checklist?: Record<string, string>) {
  return request<null>({
    url: `/api/inspections/${id}/review`,
    method: 'POST',
    data: { approved, remark, requirements, checklist },
  })
}

/** AI 辅助审核分析（需启用 AI 配置） */
export function analyzeInspectionAI(id: number) {
  return request<{ analysis: string }>({ url: `/api/inspections/${id}/ai-analyze`, method: 'POST' })
}

// ==================== 巡检审核检查项清单（V23） ====================
export interface ReviewChecklistItem {
  name: string
  enabled: boolean
}

export function fetchReviewChecklist() {
  return request<{ items: ReviewChecklistItem[] }>({
    url: '/api/system/inspection-review-checklist',
    method: 'GET',
  })
}

export function updateReviewChecklist(items: ReviewChecklistItem[]) {
  return request<{ items: ReviewChecklistItem[] }>({
    url: '/api/system/inspection-review-checklist',
    method: 'PUT',
    data: { items },
  })
}

/** 从任务上传巡检报告（multipart：report_file + conclusion）→ 自动建记录/版本并提交审核 */
export interface UploadTaskReportResult {
  inspection_id: number
  version_no: number
  task_status: string
  config_backups: number
  topologies: number
  skipped: Array<[string, string]>
  asset_import: { created: number; updated: number; skipped: number; errors: string[]; filename: string } | null
}

/** 从任务上传全套资料（multipart）→ 自动建记录/版本并提交审核 */
export function uploadTaskReport(taskId: number, formData: FormData) {
  return request<UploadTaskReportResult>({
    url: `/api/inspections/task/${taskId}/report`,
    method: 'POST',
    data: formData,
  })
}

/** 提交资料文件下载地址（GET）——挂 submission_assets（配置包/拓扑图/资产清单） */
export function submissionAssetUrl(assetId: number) {
  return `/api/inspections/assets/${assetId}/download`
}

/** 配置文本在线查看（挂 submission_assets） */
export function fetchSubmissionAssetContent(assetId: number) {
  return request<{ content: string }>({ url: `/api/inspections/assets/${assetId}/content`, method: 'GET' })
}

export function fetchInspectionVersions(id: number) {
  return request<SubmissionVersion[]>({ url: `/api/inspections/${id}/versions`, method: 'GET' })
}

/** 版本报告下载地址（GET） */
export function versionReportUrl(entityType: 'inspection' | 'ticket', versionId: number) {
  return entityType === 'inspection'
    ? `/api/inspections/report/${versionId}`
    : `/api/tickets/report/${versionId}`
}

/** 正式 Word 报告下载地址（审核通过自动生成，存 reports/） */
export function formalReportUrl(filename: string) {
  return `/reports/${encodeURIComponent(filename)}`
}

export interface InspectionTaskOption {
  id: number
  title: string
  status: string
  customer_id: number
  customer_name: string
  assignee_id: number | null
  has_record?: boolean
}

export interface InspectionDicts {
  customers: { id: number; name: string; region_id: number | null }[]
  inspectors: { user_id: number; name: string }[]
  tasks: InspectionTaskOption[]
  overall_statuses: string[]
  review_statuses: string[]
}

export function fetchInspectionDicts() {
  return request<InspectionDicts>({ url: '/api/dicts/inspections', method: 'GET' })
}

/** 巡检记录导出 URL（SSR，带筛选参数） */
export function inspectionExportUrl(params: Record<string, unknown>) {
  return buildQueryUrl('/inspections/export', params)
}

export function inspectionReportsZipUrl(params: Record<string, unknown>) {
  return buildQueryUrl('/inspections/reports-zip', params)
}
