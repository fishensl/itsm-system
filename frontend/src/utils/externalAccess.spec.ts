import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'

describe('外网敏感配置访问', () => {
  it('配置下载走带令牌的同源请求，不使用裸链接', () => {
    const source = readFileSync(resolve(process.cwd(), 'src/views/devices/index.vue'), 'utf8')
    expect(source).toContain('requestProtectedBlob(deviceConfigBackupDownloadUrl(row.id))')
    expect(source).not.toContain('window.open(deviceConfigBackupDownloadUrl')
    const request = readFileSync(resolve(process.cwd(), 'src/utils/request.ts'), 'utf8')
    expect(request).toMatch(/if \(method !== 'GET'\) \{[^}]*\}\s*const operationToken = currentOperationToken\(\)/)
    expect(request).toContain("body.message === '需要操作动态码验证'")
  })
  it('默认首页复用外网工作台的工单入口', () => {
    const source = readFileSync(resolve(process.cwd(), 'src/router/index.ts'), 'utf8')
    expect(source).toContain("if (to.path === '/')")
    expect(source).toContain("entry === '/app/tickets' || entry === '/tickets'")
  })
})
