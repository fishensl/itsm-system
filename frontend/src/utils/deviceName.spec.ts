import { describe, expect, it } from 'vitest'
import { inactiveDeviceColor } from './deviceName'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'

describe('停用设备名称', () => {
  it('仅明确停用标灰，不改变在用及无状态手动设备', () => {
    expect(inactiveDeviceColor(false)).toBe('var(--el-text-color-placeholder)')
    for (const value of [true, null, undefined]) expect(inactiveDeviceColor(value)).toBeUndefined()
  })
  it('机柜图和设备表共用同一名称颜色', () => {
    const source = readFileSync(resolve(process.cwd(), 'src/views/rack/index.vue'), 'utf8')
    expect(source).toContain('inactiveDeviceColor(row.install.is_in_use)')
    expect(source).toContain('inactiveDeviceColor(row.is_in_use)')
    expect(source).toContain('#cell-name="{ row }"')
  })
})
