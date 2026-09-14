export interface EngineerOption {
  id: number | string
  name: string
}

/** 当前登录账号的工程师列置顶（其余保持原序），"未指派"列恒为最后。 */
export function orderEngineersForSelf(
  engineers: EngineerOption[],
  myId?: number | null,
): EngineerOption[] {
  const me = myId != null ? engineers.find((e) => e.id === myId) : undefined
  const rest = engineers.filter((e) => e !== me)
  return [...(me ? [me] : []), ...rest, { id: '__unassigned__', name: '未指派' }]
}
