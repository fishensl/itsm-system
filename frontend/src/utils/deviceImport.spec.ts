import { describe, expect, it } from 'vitest'
import { deviceImportNoActionMessage, hasExecutableDeviceImport } from '@/utils/deviceImport'

describe('deviceImport', () => {
  it('新增或更新至少一条时允许执行', () => {
    expect(hasExecutableDeviceImport({ create: 1, update: 0, unchanged: 0, skipped: 0, failed: 0 })).toBe(true)
    expect(hasExecutableDeviceImport({ create: 0, update: 2, unchanged: 0, skipped: 3, failed: 0 })).toBe(true)
  })

  it('全量跳过时不允许执行，并说明仅更新模式的正式设备边界', () => {
    const preview = { create: 0, update: 0, unchanged: 0, skipped: 37, failed: 0 }
    expect(hasExecutableDeviceImport(preview)).toBe(false)
    expect(deviceImportNoActionMessage(preview, 'update')).toContain('机柜图中的手工记录不属于设备资产')
    expect(deviceImportNoActionMessage(preview, 'update')).toContain('仅新增')
  })

  it('全部无变化时提示无需再次执行', () => {
    const preview = { create: 0, update: 0, unchanged: 4, skipped: 0, failed: 0 }
    expect(deviceImportNoActionMessage(preview, 'upsert')).toContain('没有需要执行的变更')
  })
})
