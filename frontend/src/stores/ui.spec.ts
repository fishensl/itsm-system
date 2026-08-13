import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { useUiStore } from '@/stores/ui'

describe('ui store theme', () => {
  beforeEach(() => {
    localStorage.clear()
    document.documentElement.classList.remove('dark')
    document.documentElement.style.colorScheme = ''
    vi.stubGlobal('matchMedia', vi.fn().mockReturnValue({
      matches: true,
      addEventListener: vi.fn(),
    }))
    setActivePinia(createPinia())
  })

  it('defaults to system preference and applies it before mount', () => {
    const store = useUiStore()
    store.initTheme()

    expect(store.themePreference).toBe('system')
    expect(store.effectiveTheme).toBe('dark')
    expect(document.documentElement.classList.contains('dark')).toBe(true)
    expect(document.documentElement.style.colorScheme).toBe('dark')
  })

  it('persists explicit modes and cycles through all three states', () => {
    const store = useUiStore()
    store.initTheme()

    store.setTheme('light')
    expect(localStorage.getItem('appTheme')).toBe('light')
    expect(document.documentElement.classList.contains('dark')).toBe(false)

    store.cycleTheme()
    expect(store.themePreference).toBe('dark')
    store.cycleTheme()
    expect(store.themePreference).toBe('system')
  })
})
