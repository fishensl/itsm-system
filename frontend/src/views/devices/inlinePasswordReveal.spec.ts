import { afterEach, describe, expect, it, vi } from 'vitest'
import { DEVICE_PRESETS } from '@/utils/exportColumns'
import {
  createInlinePasswordReveal, DEVICE_PASSWORD_MASK, DEVICE_VIEW_KEYS,
} from './inlinePasswordReveal'

describe('设备密码表行内显示', () => {
  afterEach(() => {
    vi.useRealTimers()
  })

  it('设备管理只提供三种正式表格快速视图', () => {
    expect(DEVICE_PRESETS
      .filter((preset) => DEVICE_VIEW_KEYS.includes(preset.key as typeof DEVICE_VIEW_KEYS[number]))
      .map((preset) => preset.label),
    ).toEqual(['设备资产表', '设备密码表', '网络安全版本控制表'])
  })

  it('默认掩码显示，点击后只显示当前设备并可主动隐藏', async () => {
    const reveal = vi.fn(async (deviceId: number) => ({ password: `pwd-${deviceId}` }))
    const state = createInlinePasswordReveal(reveal)

    expect(state.displayValue(1, true)).toBe(DEVICE_PASSWORD_MASK)
    expect(state.displayValue(2, false)).toBe('-')

    await state.toggle(1)
    expect(reveal).toHaveBeenCalledWith(1)
    expect(state.displayValue(1, true)).toBe('pwd-1')
    expect(state.displayValue(2, true)).toBe(DEVICE_PASSWORD_MASK)

    await state.toggle(1)
    expect(state.displayValue(1, true)).toBe(DEVICE_PASSWORD_MASK)
  })

  it('60 秒后自动清除行内明文', async () => {
    vi.useFakeTimers()
    const state = createInlinePasswordReveal(async () => ({ password: 'temporary-secret' }))

    await state.toggle(9)
    expect(state.displayValue(9, true)).toBe('temporary-secret')
    vi.advanceTimersByTime(60_000)
    expect(state.displayValue(9, true)).toBe(DEVICE_PASSWORD_MASK)
  })

  it('切换视图后忽略尚未完成的查看请求', async () => {
    let resolveReveal: ((value: { password: string }) => void) | undefined
    const state = createInlinePasswordReveal(() => new Promise((resolve) => {
      resolveReveal = resolve
    }))

    const pending = state.toggle(3)
    state.clear()
    resolveReveal?.({ password: 'late-secret' })
    await pending

    expect(state.displayValue(3, true)).toBe(DEVICE_PASSWORD_MASK)
  })
})
