/**
 * 响应式断点：桌面/移动端切换（与 DataTable 的 matchMedia 一致）
 */
import { ref, onMounted, onBeforeUnmount } from 'vue'

const MOBILE_QUERY = '(max-width: 767px)'

export function useMobile() {
  const isMobile = ref(false)
  let mq: MediaQueryList | null = null

  function onChange(e: MediaQueryListEvent | MediaQueryList) {
    isMobile.value = !!e.matches
  }

  onMounted(() => {
    mq = window.matchMedia(MOBILE_QUERY)
    onChange(mq)
    mq.addEventListener('change', onChange)
  })
  onBeforeUnmount(() => {
    mq?.removeEventListener('change', onChange)
  })

  return { isMobile }
}
