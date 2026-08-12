import request from '@/utils/request'

export interface EntityFieldMeta {
  key: string
  label: string
  dataType: string
  group: string
  exportKey: string
  defaultVisible: boolean
  filterable: boolean
  sortable: boolean
  required: boolean
  sensitive: boolean
  width?: number
  minWidth?: number
  permission?: string
  valueMap?: Record<string, string>
}

export interface EntityExportPreset {
  key: string
  label: string
  columns: string[]
}

export interface EntityMeta {
  key: string
  label: string
  profiles: Record<string, EntityFieldMeta[]>
  exportPresets: EntityExportPreset[]
}

const cache = new Map<string, EntityMeta>()
const pending = new Map<string, Promise<EntityMeta | undefined>>()

/** 同一实体在一次页面会话内只请求一次，列表/详情/导出共用结果。 */
export async function fetchEntityMeta(entity: string): Promise<EntityMeta | undefined> {
  if (cache.has(entity)) return cache.get(entity)
  if (pending.has(entity)) return pending.get(entity)
  const promise = request<{ entities: Record<string, EntityMeta> }>({
    url: '/api/meta/entities',
    method: 'GET',
    params: { entities: entity },
  }).then((result) => {
    const metadata = result.entities[entity]
    if (metadata) cache.set(entity, metadata)
    return metadata
  }).finally(() => pending.delete(entity))
  pending.set(entity, promise)
  return promise
}

/** 批量加载同一页面使用的实体元数据，避免多表页逐表发请求。 */
export async function fetchEntityMetas(entities: string[]): Promise<Record<string, EntityMeta>> {
  const names = [...new Set(entities.filter(Boolean))]
  const missing = names.filter((name) => !cache.has(name))
  if (missing.length) {
    const result = await request<{ entities: Record<string, EntityMeta> }>({
      url: '/api/meta/entities',
      method: 'GET',
      params: { entities: missing.join(',') },
    })
    Object.entries(result.entities).forEach(([name, metadata]) => cache.set(name, metadata))
  }
  return Object.fromEntries(
    names.flatMap((name) => cache.has(name) ? [[name, cache.get(name)!]] : []),
  )
}

/** 保留页面特有渲染/操作，仅用注册中心覆盖通用字段展示口径。 */
export function mergeFieldMeta<T extends {
  key: string
  label: string
  width?: number
  minWidth?: number
  defaultVisible?: boolean
  group?: string
  valueMap?: Record<string, string>
}>(columns: T[], fields: EntityFieldMeta[]): T[] {
  if (!fields.length) return columns
  const metadata = new Map(fields.map((item) => [item.key, item]))
  return columns.map((column) => {
    const item = metadata.get(column.key)
    if (!item) return column
    return {
      ...column,
      label: item.label,
      width: item.width ?? column.width,
      minWidth: item.minWidth ?? column.minWidth,
      defaultVisible: item.defaultVisible,
      group: item.group || column.group,
      valueMap: item.valueMap ?? column.valueMap,
    }
  })
}

/** 详情/表单/内嵌表格读取统一标签；元数据不可用时保留页面兜底文案。 */
export function entityFieldLabel(
  metadata: EntityMeta | undefined,
  key: string,
  fallback: string,
  profile = 'detail',
): string {
  const fields = metadata?.profiles[profile] || []
  return fields.find((item) => item.key === key)?.label || fallback
}
