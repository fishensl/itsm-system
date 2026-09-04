<template>
  <el-dialog
    :model-value="modelValue"
    :fullscreen="fullscreen"
    :width="dialogWidth"
    :style="dialogStyle"
    class="adaptive-preview-dialog"
    top="3vh"
    append-to-body
    destroy-on-close
    :show-close="false"
    @update:model-value="emit('update:modelValue', $event)"
    @closed="onClosed"
  >
    <template #header="{ close, titleId, titleClass }">
      <div class="adaptive-preview-header">
        <span :id="titleId" :class="titleClass" class="adaptive-preview-title">{{ title }}</span>
        <span v-if="!fullscreen" class="resize-hint">拖动右下角可调整大小</span>
        <div class="preview-window-actions">
          <el-button text :icon="fullscreen ? CopyDocument : FullScreen" @click="fullscreen = !fullscreen">
            {{ fullscreen ? '还原' : '全屏' }}
          </el-button>
          <el-button text :icon="Close" aria-label="关闭预览" @click="close" />
        </div>
      </div>
    </template>

    <div class="adaptive-preview-content">
      <slot />
    </div>

    <template v-if="$slots.footer" #footer>
      <slot name="footer" />
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { Close, CopyDocument, FullScreen } from '@element-plus/icons-vue'

const props = withDefaults(defineProps<{
  modelValue: boolean
  title: string
  startWidth?: number
  startHeight?: number
}>(), {
  startWidth: 1120,
  startHeight: 760,
})

const emit = defineEmits<{
  'update:modelValue': [value: boolean]
  closed: []
}>()

const fullscreen = ref(false)
const dialogWidth = computed(() => fullscreen.value
  ? undefined
  : `min(${props.startWidth}px, calc(100vw - 32px))`)
const dialogStyle = computed(() => fullscreen.value
  ? undefined
  : { height: `min(${props.startHeight}px, calc(94vh - 24px))` })

function onClosed() {
  fullscreen.value = false
  emit('closed')
}
</script>

<style>
.adaptive-preview-dialog {
  display: flex;
  flex-direction: column;
  max-width: calc(100vw - 24px);
  max-height: 94vh;
  margin-bottom: 0;
  overflow: hidden;
}
.adaptive-preview-dialog:not(.is-fullscreen) {
  min-width: min(640px, calc(100vw - 24px));
  min-height: min(480px, calc(100vh - 24px));
  resize: both;
}
.adaptive-preview-dialog .el-dialog__header {
  flex-shrink: 0;
  padding: 10px 14px;
  border-bottom: 1px solid var(--el-border-color-lighter);
}
.adaptive-preview-dialog .el-dialog__body {
  flex: 1;
  min-height: 0;
  padding: 10px 14px;
  overflow: hidden;
}
.adaptive-preview-dialog .el-dialog__footer {
  flex-shrink: 0;
  padding: 8px 14px 10px;
  border-top: 1px solid var(--el-border-color-lighter);
}
.adaptive-preview-header {
  display: flex;
  align-items: center;
  gap: 12px;
  min-width: 0;
}
.adaptive-preview-title {
  min-width: 0;
  overflow: hidden;
  font-weight: 600;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.resize-hint {
  color: var(--el-text-color-placeholder);
  font-size: 11px;
  white-space: nowrap;
}
.preview-window-actions {
  display: flex;
  align-items: center;
  margin-left: auto;
}
.adaptive-preview-content {
  width: 100%;
  height: 100%;
  min-height: 0;
  overflow: auto;
}

@media (max-width: 767px) {
  .adaptive-preview-dialog:not(.is-fullscreen) {
    width: calc(100vw - 16px) !important;
    min-width: 0;
    height: calc(100vh - 32px) !important;
    min-height: 0;
    max-height: calc(100vh - 16px);
    resize: none;
  }
  .resize-hint { display: none; }
}
</style>
