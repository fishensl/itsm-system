import { fileURLToPath, URL } from 'node:url'
import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import AutoImport from 'unplugin-auto-import/vite'
import Components from 'unplugin-vue-components/vite'

// Element Plus 深路径按需解析：v28 resolver 默认生成主入口导入（element-plus/es）会拉全量，
// 这里覆写为组件级深路径，保证 rollup tree-shake 只打包实际使用的组件。
const EP_SPECIAL_DIRS: Record<string, string> = {
  ElTableColumn: 'table',
  ElTableV2: 'table-v2',
  ElSelectV2: 'select-v2',
  ElDescriptionsItem: 'descriptions',
  ElTimelineItem: 'timeline',
  ElCollapseItem: 'collapse',
  ElDropdownItem: 'dropdown',
  ElDropdownMenu: 'dropdown',
  ElOptionGroup: 'select',
  ElOption: 'select',
  ElCheckboxButton: 'checkbox',
  ElCheckboxGroup: 'checkbox',
  ElRadioButton: 'radio',
  ElRadioGroup: 'radio',
  ElTabPane: 'tabs',
  ElButtonGroup: 'button',
  ElInputNumber: 'input-number',
  ElScrollbar: 'scrollbar',
  ElFormItem: 'form',
}

function deepElementPlusResolver() {
  return {
    type: 'component' as const,
    resolve(name: string) {
      if (!name.startsWith('El') || !name[2]?.match(/[A-Z]/)) return
      if (name !== 'ElIcon' && name.startsWith('ElIcon')) {
        return { name: name.slice(2), from: '@element-plus/icons-vue' }
      }
      const dir = EP_SPECIAL_DIRS[name] || name.slice(2)
        .replace(/([a-z0-9])([A-Z])/g, '$1-$2')
        .replace(/([A-Z])([A-Z][a-z])/g, '$1-$2')
        .toLowerCase()
      return {
        name,
        from: `element-plus/es/components/${dir}/index`,
        sideEffects: [`element-plus/es/components/${dir}/style/css`],
      }
    },
  }
}

// SPA 挂载在 /app/ 前缀下（与 Flask SSR 双轨并存）
export default defineConfig({
  base: '/app/',
  plugins: [
    vue(),
    AutoImport({
      resolvers: [deepElementPlusResolver()],
      dts: false,
    }),
    Components({
      resolvers: [deepElementPlusResolver()],
      dts: false,
    }),
  ],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
    },
  },
  server: {
    port: 5173,
    proxy: {
      // 开发时 API 与静态资源代理到 Flask
      '/api': { target: 'http://127.0.0.1:5000', changeOrigin: true },
      '/static': { target: 'http://127.0.0.1:5000', changeOrigin: true },
      '/uploads': { target: 'http://127.0.0.1:5000', changeOrigin: true },
    },
  },
  build: {
    outDir: 'dist',
    assetsDir: 'assets',
    rollupOptions: {
      output: {
        manualChunks(id) {
          if (id.includes('node_modules')) {
            if (id.includes('element-plus') || id.includes('@element-plus')) return 'element-plus'
            if (id.includes('vue') || id.includes('pinia') || id.includes('vue-router')) return 'vue-vendor'
            if (id.includes('axios')) return 'axios'
            return 'vendor'
          }
        },
      },
    },
  },
})
