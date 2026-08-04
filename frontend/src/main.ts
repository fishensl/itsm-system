import { createApp } from 'vue'
import { createPinia } from 'pinia'
import ElementPlus from 'element-plus'
import 'element-plus/dist/index.css'
import 'element-plus/theme-chalk/dark/css-vars.css'
import zhCn from 'element-plus/es/locale/lang/zh-cn'
import * as ElementPlusIconsVue from '@element-plus/icons-vue'

import App from './App.vue'
import router from './router'
import { useUiStore } from './stores/ui'
import './styles/index.css'

const app = createApp(App)

app.use(createPinia())
app.use(router)
app.use(ElementPlus, { locale: zhCn })

for (const [key, component] of Object.entries(ElementPlusIconsVue)) {
  app.component(key, component)
}

// 全局 toast 事件桥（供 axios 拦截器等非组件代码触发）
window.addEventListener('itsm:toast', ((e: CustomEvent<{ message: string; type?: string }>) => {
  const ui = useUiStore()
  ui.toast(e.detail.message, (e.detail.type as 'success' | 'error' | 'warning' | 'info') || 'info')
}) as EventListener)

app.mount('#app')
