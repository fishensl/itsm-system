<template>
  <div class="file-preview" :class="{ 'has-content': !!content }">
    <!-- 图片 -->
    <img v-if="kind === 'image' && objectUrl" :src="objectUrl" class="preview-image" alt="预览" />
    <!-- PDF -->
    <iframe v-else-if="kind === 'pdf' && objectUrl" :src="objectUrl" class="preview-frame" title="PDF 预览" />
    <!-- Word（docx-preview 渲染） -->
    <div v-else-if="kind === 'docx'" ref="docxBox" class="preview-docx" />
    <!-- 文本 -->
    <pre v-else-if="kind === 'text' && content" class="preview-text">{{ content }}</pre>
    <!-- 不支持的类型 -->
    <el-empty v-else-if="kind === 'other'" :description="`${ext} 类型暂不支持在线预览，请下载查看`" :image-size="60">
      <el-button type="primary" size="small" :icon="Download" @click="download">下载文件</el-button>
    </el-empty>
    <el-empty v-else description="加载中..." :image-size="40" />
  </div>
</template>

<script setup lang="ts">
import { ref, watch, onBeforeUnmount, computed } from 'vue'
import { Download } from '@element-plus/icons-vue'

const props = defineProps<{
  url?: string
  fileName?: string
  /** 直接文本内容（文本配置预览，无需请求） */
  text?: string
}>()

const objectUrl = ref('')
const docxBox = ref<HTMLElement>()
const content = ref('')

const ext = computed(() => {
  const name = (props.fileName || props.url?.split('?')[0].split('/').pop() || '').toLowerCase()
  return (name.includes('.') ? name.split('.').pop()! : '').toLowerCase()
})
const kind = computed(() => {
  if (props.text !== undefined) return 'text'
  const e = ext.value
  if (['png', 'jpg', 'jpeg', 'gif', 'bmp', 'webp'].includes(e)) return 'image'
  if (e === 'pdf') return 'pdf'
  if (['doc', 'docx'].includes(e)) return 'docx'
  if (['txt', 'cfg', 'conf', 'log', 'text'].includes(e)) return 'text'
  return 'other'
})

async function load() {
  cleanup()
  content.value = ''
  const k = kind.value
  if (k === 'other') return
  if (k === 'text' && props.text !== undefined) {
    content.value = props.text
    return
  }
  try {
    const resp = await fetch(props.url!, { credentials: 'same-origin' })
    if (!resp.ok) throw new Error('加载失败')
    const blob = await resp.blob()
    if (k === 'docx') {
      const { renderAsync } = await import('docx-preview')
      const buf = await blob.arrayBuffer()
      const box = docxBox.value
      if (box) {
        box.innerHTML = ''
        await renderAsync(buf, box, undefined, {
          className: 'docx',
          inWrapper: true,
          ignoreWidth: true,
          ignoreHeight: false,
          breakPages: true,
          experimental: true,
        })
      }
      return
    }
    if (k === 'text') {
      content.value = await blob.text()
      return
    }
    // 图片/PDF：Blob URL（type 兜底按扩展名）
    const mime = k === 'pdf' ? 'application/pdf' : undefined
    objectUrl.value = URL.createObjectURL(mime ? new Blob([blob], { type: mime }) : blob)
  } catch { /* 静默失败：保持空 */ }
}

function cleanup() {
  if (objectUrl.value) {
    URL.revokeObjectURL(objectUrl.value)
    objectUrl.value = ''
  }
  if (docxBox.value) docxBox.value.innerHTML = ''
}

function download() {
  window.open(props.url, '_blank')
}

watch(() => [props.url, props.text], load, { immediate: true })
onBeforeUnmount(cleanup)
</script>

<style scoped>
.file-preview { min-height: 200px; }
.has-content { height: 100%; }
.preview-image { max-width: 100%; display: block; margin: 0 auto; }
.preview-frame { width: 100%; height: 100%; min-height: 420px; border: 1px solid var(--el-border-color-lighter); }
.preview-docx { max-height: 62vh; overflow: auto; border: 1px solid var(--el-border-color-lighter); border-radius: 4px; }
.preview-text {
  max-height: 62vh; overflow: auto; margin: 0; padding: 10px; font-size: 12px; line-height: 1.6;
  background: var(--el-fill-color-light); border-radius: 4px; white-space: pre-wrap; word-break: break-all;
}
</style>
