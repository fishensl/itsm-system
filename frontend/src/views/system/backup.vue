<template>
  <div class="page-container">
    <div class="page-header">
      <h2 class="page-title">数据备份 / 恢复</h2>
    </div>

    <el-row :gutter="12">
      <el-col :xs="24" :md="12">
        <el-card shadow="never">
          <template #header><b>当前库概要</b></template>
          <div v-loading="loading">
            <el-descriptions :column="2" border size="small">
              <el-descriptions-item v-for="(label, key) in STAT_LABELS" :key="key" :label="label">
                {{ stats?.[key] ?? '-' }}
              </el-descriptions-item>
            </el-descriptions>
            <div class="file-size">上传文件约 <b>{{ fileSizeMb }}</b> MB（reports / uploads / static/uploads）</div>
          </div>
        </el-card>
      </el-col>

      <el-col :xs="24" :md="12">
        <el-card shadow="never">
          <template #header><b>导出备份</b></template>
          <el-form label-width="120px">
            <el-form-item label="范围">
              <el-radio-group v-model="exportConfigOnly">
                <el-radio :value="false">全量数据</el-radio>
                <el-radio :value="true">仅配置</el-radio>
              </el-radio-group>
            </el-form-item>
            <el-form-item label="加密密码">
              <el-input v-model="exportPassword" type="password" show-password placeholder="可选：整包加密" />
            </el-form-item>
            <el-form-item>
              <el-button type="primary" :loading="exporting" @click="onExport">导出备份包</el-button>
            </el-form-item>
          </el-form>
        </el-card>

        <el-card shadow="never" class="mt-3">
          <template #header><b>导入恢复（危险）</b></template>
          <el-form label-width="120px">
            <el-form-item label="备份文件">
              <input ref="fileInput" type="file" accept=".zip" class="file-input" />
            </el-form-item>
            <el-form-item label="还原密钥">
              <el-checkbox v-model="restoreKey">同时还原 .secret.key 加密密钥</el-checkbox>
            </el-form-item>
            <el-form-item label="加密密码">
              <el-input v-model="importPassword" type="password" show-password placeholder="备份包加密密码（如有）" />
            </el-form-item>
            <el-form-item label="二次确认">
              <el-input v-model="confirmText" placeholder='输入"我确认覆盖"' />
              <div class="warn">导入将清空并覆盖全部现有数据！</div>
            </el-form-item>
            <el-form-item>
              <el-button type="danger" :disabled="confirmText !== '我确认覆盖'" :loading="importing"
                @click="onImport">执行导入</el-button>
            </el-form-item>
          </el-form>
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<script setup lang="ts">
import { ElMessageBox } from 'element-plus/es/components/message-box/index'
import { ref, onMounted } from 'vue'
import { exportBackup, fetchBackupStats, importBackup } from '@/api/system'
import { useUiStore } from '@/stores/ui'

const ui = useUiStore()
const loading = ref(false)
const stats = ref<Record<string, number> | null>(null)
const fileSizeMb = ref('0')

const exportConfigOnly = ref(false)
const exportPassword = ref('')
const exporting = ref(false)

const fileInput = ref<HTMLInputElement>()
const restoreKey = ref(false)
const importPassword = ref('')
const confirmText = ref('')
const importing = ref(false)

const STAT_LABELS: Record<string, string> = {
  user: '用户', customer: '客户', device: '设备', ticket: '工单',
  inspection: '巡检', fault: '故障', kb: '知识库', spare: '备件', topology: '拓扑',
}

function load() {
  loading.value = true
  fetchBackupStats()
    .then((d) => {
      stats.value = d.stats
      fileSizeMb.value = String(d.file_size_mb)
    })
    .catch(() => { /* toast */ })
    .finally(() => { loading.value = false })
}

function downloadFromBase64(b64: string, filename: string) {
  const bin = atob(b64)
  const bytes = new Uint8Array(bin.length)
  for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i)
  const blob = new Blob([bytes], { type: 'application/zip' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  a.click()
  URL.revokeObjectURL(url)
}

async function onExport() {
  try {
    await ElMessageBox.confirm('确定导出备份包吗？', '导出确认', { type: 'info' })
  } catch { return }
  exporting.value = true
  try {
    const r = await exportBackup({ config_only: exportConfigOnly.value, password: exportPassword.value || undefined })
    downloadFromBase64(r.content, r.filename)
    ui.toast('备份包已生成', 'success')
  } catch (e) {
    ui.toast((e as Error).message, 'error')
  } finally {
    exporting.value = false
  }
}

async function onImport() {
  const file = fileInput.value?.files?.[0]
  if (!file) {
    ui.toast('请选择 .zip 备份文件', 'error')
    return
  }
  try {
    await ElMessageBox.confirm('导入将清空并覆盖全部现有数据，确定继续吗？', '危险操作', { type: 'warning' })
  } catch { return }
  importing.value = true
  try {
    const fd = new FormData()
    fd.append('backup_file', file)
    fd.append('confirm', confirmText.value)
    fd.append('restore_secret_key', restoreKey.value ? '1' : '0')
    if (importPassword.value) fd.append('password', importPassword.value)
    const r = await importBackup(fd)
    ui.toast(r.message, 'success')
    load()
  } catch (e) {
    ui.toast((e as Error).message, 'error')
  } finally {
    importing.value = false
  }
}

onMounted(load)
</script>

<style scoped>
.file-size { margin-top: 10px; font-size: 13px; color: var(--itsm-text-muted); }
.file-input { width: 100%; }
.warn { font-size: 12px; color: var(--el-color-danger); margin-top: 4px; }
.mt-3 { margin-top: 12px; }
</style>
