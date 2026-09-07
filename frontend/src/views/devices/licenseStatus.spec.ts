import { describe, expect, it } from 'vitest'
import { licenseStatus } from './licenseStatus'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'

describe('授权到期提示', () => {
  it('授权列使用提示渲染，快捷类别同步到树及两类导出', () => {
    const source = readFileSync(resolve(process.cwd(), 'src/views/devices/index.vue'), 'utf8')
    expect(source).toMatch(/key: 'license_expiry'[^\n]*type: 'custom'/)
    expect(source).toContain('licenseStatus(r.license_remaining_days)')
    expect(source.match(/device_category: query.device_category as string \|\| undefined/g)).toHaveLength(3)
    expect(source).toContain('query.device_type = \'\'')
    expect(source).toContain('deviceCategories.value = d.device_categories || []')
  })
  it('区分过期、当天、临期及正常，并保留文字而非只用颜色', () => {
    expect(licenseStatus(-165)).toEqual({ text: '已过期 165 天', color: 'var(--el-color-danger)' })
    expect(licenseStatus(0)?.text).toBe('今日到期')
    expect(licenseStatus(30)?.color).toBe('var(--el-color-warning)')
    expect(licenseStatus(31)?.color).toBe('var(--itsm-text-muted)')
    expect(licenseStatus(null)).toBeNull()
    expect(licenseStatus(undefined)).toBeNull()
  })
})
