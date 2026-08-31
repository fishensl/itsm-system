import { ref } from 'vue'

export const DEVICE_PASSWORD_MASK = '******'
export const DEVICE_VIEW_KEYS = ['asset', 'password', 'version'] as const

export function createInlinePasswordReveal(
  reveal: (deviceId: number) => Promise<{ password: string }>,
  timeoutMs = 60_000,
) {
  const deviceId = ref<number | null>(null)
  const value = ref('')
  const loadingId = ref<number | null>(null)
  let timer: ReturnType<typeof setTimeout> | null = null
  let generation = 0

  function clear() {
    generation += 1
    if (timer) clearTimeout(timer)
    timer = null
    deviceId.value = null
    value.value = ''
    loadingId.value = null
  }

  function displayValue(targetId: number, hasPassword: boolean) {
    if (!hasPassword) return '-'
    return deviceId.value === targetId ? (value.value || '（空）') : DEVICE_PASSWORD_MASK
  }

  async function toggle(targetId: number) {
    if (deviceId.value === targetId) {
      clear()
      return
    }
    clear()
    const currentGeneration = generation
    loadingId.value = targetId
    try {
      const result = await reveal(targetId)
      if (currentGeneration !== generation) return
      deviceId.value = targetId
      value.value = result.password || ''
      loadingId.value = null
      timer = setTimeout(clear, timeoutMs)
    } catch (error) {
      if (currentGeneration !== generation) return
      clear()
      throw error
    }
  }

  return { deviceId, loadingId, displayValue, toggle, clear }
}
