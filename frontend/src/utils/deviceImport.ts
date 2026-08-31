export interface DeviceImportCounts {
  create: number
  update: number
  unchanged: number
  skipped: number
  failed: number
}

export type DeviceImportMode = 'create' | 'update' | 'upsert'

export function hasExecutableDeviceImport(preview: DeviceImportCounts | null | undefined) {
  return Boolean(preview && preview.create + preview.update > 0)
}

export function deviceImportNoActionMessage(
  preview: DeviceImportCounts | null | undefined,
  mode: DeviceImportMode,
) {
  if (!preview || preview.failed || hasExecutableDeviceImport(preview)) return ''
  if (preview.skipped && mode === 'update') {
    return '本次没有可更新的正式设备。机柜图中的手工记录不属于设备资产，请改选“仅新增”或“新增并更新”后重新预检。'
  }
  if (preview.skipped && mode === 'create') {
    return '本次没有可新增的设备，文件中的设备均已存在。需要覆盖现有字段时，请改选“仅更新”或“新增并更新”后重新预检。'
  }
  if (preview.unchanged) return '本次文件与系统数据一致，没有需要执行的变更。'
  return '本次没有可执行的设备变更，请检查导入模式和文件内容。'
}
