import { describe, expect, it } from 'vitest'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'

describe('task schedule status markers', () => {
  it('uses a larger high-contrast marker for every workflow state', () => {
    const source = readFileSync(resolve(process.cwd(), 'src/views/taskSchedule/index.vue'), 'utf8')

    expect(source).toContain('width: 12px; height: 12px')
    expect(source).toContain('box-shadow: 0 0 0 2px currentColor')
    for (const status of ['待执行', '已安排', '执行中', '待审核', '已完成', '已取消']) {
      expect(source).toContain(`.dot-${status}`)
    }
  })
})
