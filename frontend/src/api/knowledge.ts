import request from '@/utils/request'
import type { PageResult } from '@/types'

export interface KnowledgeAttachment {
  id: number
  file_name: string
  file_ext: string
  file_size: number
  uploaded_by: string
  created_at: string
}

export interface KnowledgeItem {
  id: number
  title: string
  category: string
  created_by: string
  view_count: number
  helpful_count: number
  is_published: boolean
  published_label: string
  tags: string
  created_at: string
  content?: string
  attachments?: KnowledgeAttachment[]
}

export interface KnowledgeQuery {
  page?: number
  page_size?: number
  search?: string
  category?: string
  is_published?: number
}

export const KNOWLEDGE_CATEGORIES = ['故障案例', '设备手册', '内部规范', '巡检经验']

export const KNOWLEDGE_CATEGORY_TAG: Record<string, 'primary' | 'success' | 'warning' | 'danger' | 'info'> = {
  故障案例: 'danger',
  设备手册: 'primary',
  内部规范: 'info',
  巡检经验: 'success',
}

export function fetchKnowledgeList(params: KnowledgeQuery) {
  return request<PageResult<KnowledgeItem>>({ url: '/api/knowledge-base', method: 'GET', params })
}

export function fetchKnowledge(id: number) {
  return request<KnowledgeItem>({ url: `/api/knowledge-base/${id}`, method: 'GET' })
}

export function createKnowledge(data: Record<string, unknown>) {
  return request<{ id: number }>({ url: '/api/knowledge-base', method: 'POST', data })
}

export function updateKnowledge(id: number, data: Record<string, unknown>) {
  return request<{ id: number }>({ url: `/api/knowledge-base/${id}`, method: 'PUT', data })
}

export function deleteKnowledge(id: number) {
  return request<null>({ url: `/api/knowledge-base/${id}`, method: 'DELETE' })
}

/** 附件：上传（multipart 多文件字段 files） */
export function uploadKnowledgeAttachments(kbId: number, files: File[]) {
  const fd = new FormData()
  files.forEach((f) => fd.append('files', f))
  return request<{ added: number; attachments: KnowledgeAttachment[] }>({
    url: `/api/knowledge-base/${kbId}/attachments`,
    method: 'POST',
    data: fd,
  })
}

export function deleteKnowledgeAttachment(kbId: number, attId: number) {
  return request<null>({ url: `/api/knowledge-base/${kbId}/attachments/${attId}`, method: 'DELETE' })
}

/** 附件在线预览（内联文件流，FilePreview 组件渲染） */
export function knowledgeAttachmentPreviewUrl(kbId: number, attId: number) {
  return `/api/knowledge-base/${kbId}/attachments/${attId}/preview`
}

/** 附件下载（原文件名） */
export function knowledgeAttachmentDownloadUrl(kbId: number, attId: number) {
  return `/api/knowledge-base/${kbId}/attachments/${attId}/download`
}

export interface KnowledgeDicts {
  categories: string[]
}

export function fetchKnowledgeDicts() {
  return request<KnowledgeDicts>({ url: '/api/dicts/knowledge', method: 'GET' })
}
