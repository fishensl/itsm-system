import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'
import { parse } from '@vue/compiler-sfc'

describe('设备编辑品牌下拉', () => {
  it('编辑品牌复用系统字典并保留搜索、自定义和清空能力', () => {
    const { descriptor } = parse(readFileSync(resolve(process.cwd(), 'src/views/devices/index.vue'), 'utf8'))
    const template = descriptor.template!.content
    const select = template.match(/<el-select\s+v-model="form\.brand"[\s\S]*?<\/el-select>/)?.[0]
    expect(select).toBeTruthy()
    expect(select).toContain('filterable allow-create clearable')
    expect(select).toContain('v-for="brand in brands"')
    expect(select).toContain(':value="brand"')
    expect(template).not.toContain('<el-input v-model="form.brand"')
    expect(template).toContain('<el-input v-model="form.model"')
  })
})
