<template>
  <el-dialog :model-value="modelValue" :title="title" width="520px" destroy-on-close
    @update:model-value="emit('update:modelValue', $event)">
    <el-alert type="info" :closable="false" class="mb-2" show-icon :title="hint" />
    <div class="mb-2">
      <el-button size="small" link type="primary" @click="downloadImportTemplate(module)">
        下载导入模板
      </el-button>
    </div>
    <el-upload ref="uploadRef" drag :auto-upload="false" :limit="1" accept=".xlsx,.xls"
      :on-change="onFileChange" :on-remove="clearFile">
      <el-icon class="el-icon--upload"><UploadFilled /></el-icon>
      <div class="el-upload__text">拖拽或点击选择 Excel 文件</div>
    </el-upload>
    <template #footer>
      <el-button @click="close">取消</el-button>
      <el-button type="primary" :loading="importing" @click="doImport">开始导入</el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'
import type { UploadFile } from 'element-plus/es/components/upload'
import { ElMessageBox } from 'element-plus/es/components/message-box/index'
import { UploadFilled } from '@element-plus/icons-vue'
import { useUiStore } from '@/stores/ui'
import { downloadImportTemplate } from '@/utils/importTemplate'

export interface BatchImportResult {
  message?: string
  created?: number
  success?: number
  skipped?: number
  errors?: string[]
  total_errors?: number
  unknown_categories?: string[]
}

const props = defineProps<{
  modelValue: boolean
  title: string
  module: string
  hint: string
  importRequest: (formData: FormData) => Promise<BatchImportResult>
}>()

const emit = defineEmits<{
  'update:modelValue': [value: boolean]
  success: [result: BatchImportResult]
}>()

const ui = useUiStore()
const uploadRef = ref()
const importFile = ref<File | null>(null)
const importing = ref(false)

function onFileChange(file: UploadFile) {
  importFile.value = file.raw ?? null
}

function clearFile() {
  importFile.value = null
}

function close() {
  emit('update:modelValue', false)
}

async function doImport() {
  if (!importFile.value) {
    ui.toast('请选择 Excel 文件', 'warning')
    return
  }
  importing.value = true
  try {
    const formData = new FormData()
    formData.append('import_file', importFile.value)
    const result = await props.importRequest(formData)
    const count = result.created ?? result.success ?? 0
    const errors = result.errors || []
    const errorCount = result.total_errors ?? errors.length
    const skipped = result.skipped || 0
    const unknown = result.unknown_categories || []
    let message = result.message || `导入完成：成功 ${count} 条`
    if (skipped && !result.message) message += `，跳过/合并 ${skipped} 条`
    if (errorCount) message += `，失败 ${errorCount} 条`
    if (unknown.length) message += `；未识别单位类别（已留空）：${unknown.join('、')}`
    ui.toast(message, errorCount || unknown.length ? 'warning' : 'success')
    if (errors.length) {
      ElMessageBox.alert(errors.join('\n'), '导入错误明细', {
        customStyle: { maxHeight: '70vh', overflow: 'auto', whiteSpace: 'pre-wrap' },
      }).catch(() => {})
    }
    emit('success', result)
    close()
  } catch (error) {
    ui.toast((error as Error).message, 'error')
  } finally {
    importing.value = false
  }
}

watch(() => props.modelValue, (visible) => {
  if (!visible) {
    clearFile()
    uploadRef.value?.clearFiles?.()
  }
})
</script>
