import { describe, expect, it } from 'vitest'
import { buildRackTree } from './tree'

describe('客户机房机柜树', () => {
  it('按客户隔离同名机房和机柜，机柜号自然排序，空机房单独归组', () => {
    const rack = (id: number, name: string, location: string) =>
      ({ id, name, location, total_u: 42, color: '', install_count: 0 })
    const tree = buildRackTree([{ city: '地区', customers: [
      { id: 1, name: '客户A', racks: [rack(1, '10', '机房A'), rack(2, '2', '机房A'), rack(3, '1', '机房B'), rack(4, '1', '')] },
      { id: 2, name: '客户B', racks: [rack(5, '2', '机房A')] },
    ] }])
    expect(tree.map((node) => node.type)).toEqual(['customer', 'customer'])
    const rooms = tree[0].children!
    expect(rooms.map((node) => node.label)).toEqual(['未填写机房', '机房A', '机房B'])
    expect(rooms[1].children!.map((node) => node.label)).toEqual(['2', '10'])
    expect(rooms[1].id).not.toBe(tree[1].children![0].id)
    expect(tree[1].children![0].children).toHaveLength(1)
  })
})
