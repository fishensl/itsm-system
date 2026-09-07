import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { parse } from '@vue/compiler-sfc'
import { describe, expect, it } from 'vitest'

describe('到期授权两行布局', () => {
  it('客户独占首行，设备和到期提示在第二行，提示不被挤压', () => {
    const { descriptor } = parse(readFileSync(resolve(process.cwd(), 'src/views/dashboard/index.vue'), 'utf8'))
    const template = descriptor.template!.content
    expect(template).toMatch(/class="license-customer"[^>]*>{{ d.customer_name }}<\/div>\s*<div class="license-detail">/)
    const detail = template.match(/<div class="license-detail">([\s\S]*?)<\/div>/)![1]
    expect(detail).toContain('{{ d.device_name }}')
    expect(detail).toContain('d.remaining_days')
    expect(detail).not.toContain('d.customer_name')
    expect(descriptor.styles.map(s => s.content).join('')).toContain('.license-detail .el-tag { flex-shrink: 0; }')
  })
})
