import { defineStore } from 'pinia'
import { ref } from 'vue'

export type ToastType = 'success' | 'error' | 'warning' | 'info'

interface ToastItem {
  id: number
  message: string
  type: ToastType
}

export const useUiStore = defineStore('ui', () => {
  const toasts = ref<ToastItem[]>([])
  const sidebarCollapsed = ref(localStorage.getItem('sidebarCollapsed') === 'true')
  const mobileSidebarOpen = ref(false)

  let seq = 0

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

  return { toasts, sidebarCollapsed, mobileSidebarOpen, toast, toggleSidebar }
})
