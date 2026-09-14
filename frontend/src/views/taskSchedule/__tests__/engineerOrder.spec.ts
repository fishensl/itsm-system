import { describe, expect, it } from 'vitest'
import { orderEngineersForSelf } from '../engineerOrder'

describe('orderEngineersForSelf', () => {
  const engineers = [
    { id: 3, name: '甲' },
    { id: 7, name: '乙' },
    { id: 9, name: '丙' },
  ]

  it('本人列置顶，其余保持原序，未指派在末尾', () => {
    expect(orderEngineersForSelf(engineers, 7).map((e) => e.id))
      .toEqual([7, 3, 9, '__unassigned__'])
  })

  it('本人不在列表时保持原序', () => {
    expect(orderEngineersForSelf(engineers, 5).map((e) => e.id))
      .toEqual([3, 7, 9, '__unassigned__'])
  })

  it('未登录 id 为空时保持原序', () => {
    expect(orderEngineersForSelf(engineers, null).map((e) => e.id))
      .toEqual([3, 7, 9, '__unassigned__'])
  })

  it('空列表只返回未指派列', () => {
    expect(orderEngineersForSelf([], 3).map((e) => e.id)).toEqual(['__unassigned__'])
  })
})
