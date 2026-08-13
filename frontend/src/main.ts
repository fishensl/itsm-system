import { createApp } from 'vue'
import { createPinia } from 'pinia'
import 'element-plus/theme-chalk/dark/css-vars.css'
// JS API（ElMessage/ElMessageBox/ElNotification/ElLoading）样式：按需引入模式下需手动补充
import 'element-plus/theme-chalk/el-message.css'
import 'element-plus/theme-chalk/el-message-box.css'
import 'element-plus/theme-chalk/el-notification.css'
import 'element-plus/theme-chalk/el-loading.css'

import App from './App.vue'
import router from './router'
import { useUiStore } from './stores/ui'
import { useUserStore } from './stores/user'
import { dynamicIcons } from './utils/icons'
import './styles/index.css'

const app = createApp(App)

app.use(createPinia())
useUiStore().initTheme()
app.use(router)

// 仅注册动态字符串图标（侧栏/仪表盘/DataTable action 用 <component :is> 解析）
for (const [key, component] of Object.entries(dynamicIcons)) {
  app.component(key, component)
}

// v-perm：无权限直接移除元素（按钮级权限控制）
app.directive('perm', {
  mounted(el, binding) {
    const userStore = useUserStore()
    if (!userStore.hasPerm(binding.value as string | undefined)) {
      el.parentNode?.removeChild(el)
    }
  },
})

// 全局 toast 事件桥（供 axios 拦截器等非组件代码触发）
window.addEventListener('itsm:toast', ((e: CustomEvent<{ message: string; type?: string }>) => {
  const ui = useUiStore()
  ui.toast(e.detail.message, (e.detail.type as 'success' | 'error' | 'warning' | 'info') || 'info')
}) as EventListener)

app.mount('#app')
