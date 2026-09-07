import type { RackTreeCity } from '@/api/rack'

export interface TreeNode {
  id: string
  label: string
  type: 'customer' | 'room' | 'rack'
  color?: string
  install_count?: number
  children?: TreeNode[]
}

export function buildRackTree(cities: RackTreeCity[]): TreeNode[] {
  return cities.flatMap((city) => city.customers).map((customer): TreeNode => {
    const rooms = new Map<string, TreeNode[]>()
    for (const rack of customer.racks) {
      const room = (rack.location || '').trim()
      if (!rooms.has(room)) rooms.set(room, [])
      rooms.get(room)!.push({ id: `rack-${rack.id}`, label: rack.name,
        type: 'rack', color: rack.color, install_count: rack.install_count })
    }
    return { id: `cust-${customer.id}`, label: customer.name, type: 'customer',
      children: [...rooms.entries()].sort(([a], [b]) => a.localeCompare(b, 'zh-CN', { numeric: true }))
        .map(([room, racks]) => ({ id: `room-${customer.id}-${encodeURIComponent(room)}`,
          label: room || '未填写机房', type: 'room',
          children: racks.sort((a, b) => a.label.localeCompare(b.label, 'zh-CN', { numeric: true })) })) }
  }).sort((a, b) => a.label.localeCompare(b.label, 'zh-CN', { numeric: true }))
}
