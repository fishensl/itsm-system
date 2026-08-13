import { defineStore } from 'pinia'
import { computed, ref } from 'vue'

export type ToastType = 'success' | 'error' | 'warning' | 'info'
export type ThemePreference = 'system' | 'light' | 'dark'
export type EffectiveTheme = Exclude<ThemePreference, 'system'>

interface ToastItem {
  id: number
  message: string
  type: ToastType
}

export const useUiStore = defineStore('ui', () => {
  const toasts = ref<ToastItem[]>([])
  const sidebarCollapsed = ref(localStorage.getItem('sidebarCollapsed') === 'true')
  const mobileSidebarOpen = ref(false)
  const savedTheme = localStorage.getItem('appTheme')
  const themePreference = ref<ThemePreference>(
    savedTheme === 'light' || savedTheme === 'dark' ? savedTheme : 'system',
  )
  const systemTheme = ref<EffectiveTheme>('light')
  const effectiveTheme = computed<EffectiveTheme>(() =>
    themePreference.value === 'system' ? systemTheme.value : themePreference.value,
  )
  const themeLabel = computed(() => ({
    system: '跟随系统',
    light: '浅色',
    dark: '深色',
  })[themePreference.value])

  let seq = 0
  let mediaQuery: MediaQueryList | undefined

  function applyTheme() {
    document.documentElement.classList.toggle('dark', effectiveTheme.value === 'dark')
    document.documentElement.style.colorScheme = effectiveTheme.value
  }

  function syncSystemTheme(event?: MediaQueryListEvent) {
    systemTheme.value = (event?.matches ?? mediaQuery?.matches) ? 'dark' : 'light'
    if (themePreference.value === 'system') applyTheme()
  }

  function initTheme() {
    mediaQuery ??= window.matchMedia?.('(prefers-color-scheme: dark)')
    syncSystemTheme()
    mediaQuery?.addEventListener?.('change', syncSystemTheme)
    applyTheme()
  }

  function setTheme(preference: ThemePreference) {
    themePreference.value = preference
    localStorage.setItem('appTheme', preference)
    applyTheme()
  }

  function cycleTheme() {
    const order: ThemePreference[] = ['system', 'light', 'dark']
    setTheme(order[(order.indexOf(themePreference.value) + 1) % order.length])
  }

  function toast(message: string, type: ToastType = 'info', duration = 3000) {
    const id = ++seq
    toasts.value.push({ id, message, type })
    setTimeout(() => {
      toasts.value = toasts.value.filter((t) => t.id !== id)
    }, duration)
  }

  function toggleSidebar() {
    sidebarCollapsed.value = !sidebarCollapsed.value
    localStorage.setItem('sidebarCollapsed', String(sidebarCollapsed.value))
  }

  return {
    toasts,
    sidebarCollapsed,
    mobileSidebarOpen,
    themePreference,
    effectiveTheme,
    themeLabel,
    toast,
    toggleSidebar,
    initTheme,
    setTheme,
    cycleTheme,
  }
})
