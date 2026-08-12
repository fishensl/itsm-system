<template>
  <div class="page-container">
    <div class="page-header">
      <h2 class="page-title">数据备份 / 恢复</h2>
      <div class="header-actions">
        <el-tag :type="backupEnabled ? 'success' : 'info'" size="small">
          {{ backupEnabled ? `自动备份：每日 ${backupTime}` : '自动备份未启用' }}
        </el-tag>
      </div>
    </div>

    <!-- 1. 数据概览 -->
    <h6 class="module-title"><el-icon><DataAnalysis /></el-icon>数据概览</h6>
    <el-row :gutter="12">
      <el-col v-for="s in statCards" :key="s.label" :xs="12" :sm="6" :md="3">
        <div class="stat-card">
          <div class="stat-value">{{ s.value }}</div>
          <div class="stat-label">{{ s.label }}</div>
        </div>
      </el-col>
    </el-row>
    <div class="file-size-tip">上传文件约 <b>{{ fileSizeMb }}</b> MB（reports / uploads / static/uploads，随备份包一并导出）</div>

    <!-- 2. 导出 / 导入 / 调度 三卡并排 -->
    <el-row :gutter="12" class="mt-3">
      <el-col :xs="24" :md="8">
        <el-card shadow="never" class="op-card">
          <template #header><span class="card-title">导出备份</span></template>
          <el-form label-width="72px" label-position="left" size="small" @submit.prevent>
            <el-form-item label="范围">
              <el-radio-group v-model="exportConfigOnly" class="w-full">
                <el-radio :value="false">全量</el-radio>
                <el-radio :value="true">仅配置</el-radio>
              </el-radio-group>
            </el-form-item>
            <el-form-item label="加密密码">
              <el-input v-model="exportPassword" type="password" show-password autocomplete="new-password"
                placeholder="可选，导入时需提供" />
            </el-form-item>
            <el-form-item>
              <el-button type="primary" :loading="exporting" @click="onExport">导出备份包</el-button>
              <span class="inline-hint">全量=数据+配置+密钥+文件</span>
            </el-form-item>
          </el-form>
        </el-card>
      </el-col>

      <el-col :xs="24" :md="8">
        <el-card shadow="never" class="op-card">
          <template #header><span class="card-title danger-title">导入恢复</span></template>
          <el-form label-width="72px" label-position="left" size="small" @submit.prevent>
            <el-form-item label="备份文件">
              <input ref="fileInput" type="file" accept=".zip" class="file-input" />
            </el-form-item>
            <el-form-item label="还原密钥">
              <el-checkbox v-model="restoreKey">同时还原 .secret.key</el-checkbox>
            </el-form-item>
            <el-form-item label="加密密码">
              <el-input v-model="importPassword" type="password" show-password autocomplete="new-password" placeholder="如有" />
            </el-form-item>
            <el-form-item label="二次确认">
              <el-input v-model="confirmText" placeholder='输入"我确认覆盖"' />
            </el-form-item>
            <el-form-item>
              <el-button type="danger" plain :disabled="confirmText !== '我确认覆盖'"
                :loading="importing" @click="onImport">执行导入</el-button>
            </el-form-item>
          </el-form>
          <div class="warn">⚠ 覆盖全部数据；导入前将自动备份当前数据（backups/pre_import_*.zip）</div>
        </el-card>
      </el-col>

      <el-col :xs="24" :md="8">
        <el-card shadow="never" class="op-card">
          <template #header><span class="card-title">调度配置</span></template>
          <el-form label-width="72px" label-position="left" size="small" @submit.prevent>
            <el-form-item label="每日备份">
              <el-switch v-model="backupEnabled" />
            </el-form-item>
            <el-form-item label="备份时刻">
              <el-time-select v-model="backupTime" start="00:00" step="00:30" end="23:30"
                placeholder="03:00" class="w-full" />
            </el-form-item>
            <el-form-item label="保留份数">
              <el-input-number v-model="backupKeep" :min="1" :max="365" class="w-full" />
            </el-form-item>
            <el-form-item>
              <el-button type="primary" :loading="savingCfg" @click="onSaveConfig">保存配置</el-button>
              <span class="inline-hint">由调度器每日执行 backup.sh</span>
            </el-form-item>
          </el-form>
        </el-card>
      </el-col>
    </el-row>

    <!-- 3. 备份产物与恢复（默认收起） -->
    <el-collapse v-model="infoOpen" class="mt-3">
      <el-collapse-item name="info" title="备份产物与恢复（文件命名 / 整机恢复 / 紧急回滚命令）">
        <el-descriptions :column="2" size="small" class="kv-desc" border>
          <el-descriptions-item label="数据库备份">
            <code>itsm_pg_&lt;时间戳&gt;.dump</code>
          </el-descriptions-item>
          <el-descriptions-item label="密钥与文件">
            <code>itsm_meta_&lt;时间戳&gt;.tar.gz</code>
          </el-descriptions-item>
          <el-descriptions-item label="导入前备份">
            <code>pre_import_&lt;时间戳&gt;.zip</code>
          </el-descriptions-item>
          <el-descriptions-item label="保留策略">
            自动保留最近 <b>{{ backupKeep }}</b> 份
          </el-descriptions-item>
          <el-descriptions-item label="整机恢复">
            <code>scripts/restore.sh &lt;目录&gt; &lt;备份&gt;</code>
          </el-descriptions-item>
          <el-descriptions-item label="紧急回滚">
            <code>scripts/rollback.sh &lt;目录&gt; &lt;备份&gt;</code>
          </el-descriptions-item>
        </el-descriptions>
        <div class="field-hint mt-2">
          备份必须同时保存数据库与密钥（.secret.key）——丢密钥 = 全部设备/AI 密码不可解密。
        </div>
      </el-collapse-item>
    </el-collapse>
  </div>
</template>

<script setup lang="ts">
import { ElMessageBox } from 'element-plus/es/components/message-box/index'
import { ref, onMounted, computed } from 'vue'
import { DataAnalysis } from '@element-plus/icons-vue'
import { exportBackup, fetchBackupStats, importBackup, fetchBackupConfig, saveBackupConfig } from '@/api/system'
import { useUiStore } from '@/stores/ui'

const ui = useUiStore()
const loading = ref(false)
const stats = ref<Record<string, number> | null>(null)
const fileSizeMb = ref('0')
const infoOpen = ref([])  // 信息区默认收起

const exportConfigOnly = ref(false)
const exportPassword = ref('')
const exporting = ref(false)

const fileInput = ref<HTMLInputElement>()
const restoreKey = ref(false)
const importPassword = ref('')
const confirmText = ref('')
const importing = ref(false)

// 自动备份配置
const backupEnabled = ref(false)
const backupTime = ref('03:00')
const backupKeep = ref(30)
const savingCfg = ref(false)

const STAT_ITEMS: Array<{ key: string; label: string }> = [
  { key: 'user', label: '用户' },
  { key: 'customer', label: '客户' },
  { key: 'device', label: '设备' },
  { key: 'ticket', label: '工单' },
  { key: 'inspection', label: '巡检' },
  { key: 'fault', label: '故障' },
  { key: 'spare', label: '备件' },
  { key: 'topology', label: '拓扑' },
]
const statCards = computed(() =>
  STAT_ITEMS.map((s) => ({ ...s, value: stats.value?.[s.key] ?? 0 })),
)

function load() {
  loading.value = true
  fetchBackupStats()
    .then((d) => {
      stats.value = d.stats
      fileSizeMb.value = String(d.file_size_mb)
    })
    .catch(() => { /* toast */ })
    .finally(() => { loading.value = false })
  fetchBackupConfig()
    .then((c) => {
      backupEnabled.value = c.backup_enabled === '1'
      backupTime.value = c.backup_time || '03:00'
      backupKeep.value = Number(c.backup_keep) || 30
    })
    .catch(() => { /* toast */ })
}

function downloadByToken(token: string, filename: string) {
  // 服务端落盘 + token 一次性下载（GET，浏览器直链，避免大包 base64 回传）
  const a = document.createElement('a')
  a.href = `/api/system/backup/export-download/${token}`
  a.download = filename
  document.body.appendChild(a)
  a.click()
  a.remove()
}

async function onExport() {
  try {
    await ElMessageBox.confirm('确定导出备份包吗？', '导出确认', { type: 'info' })
  } catch { return }
  exporting.value = true
  try {
    const r = await exportBackup({ config_only: exportConfigOnly.value, password: exportPassword.value || undefined })
    downloadByToken(r.token, r.filename)
    ui.toast('备份包已生成，请在弹出的下载中保存', 'success')
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
    await ElMessageBox.confirm('导入将清空并覆盖全部现有数据，确定继续吗？\n（导入前将自动备份当前数据到 backups/）', '危险操作', { type: 'warning' })
  } catch { return }
  importing.value = true
  try {
    const fd = new FormData()
    fd.append('backup_file', file)
    fd.append('confirm', confirmText.value)
    fd.append('restore_secret_key', restoreKey.value ? '1' : '0')
    if (importPassword.value) fd.append('password', importPassword.value)
    const r = await importBackup(fd)
    const pre = r.pre_import_file ? `（导入前已自动备份：${r.pre_import_file}）` : ''
    ui.toast(`${r.message}${pre}`, 'success')
    load()
  } catch (e) {
    ui.toast((e as Error).message, 'error')
  } finally {
    importing.value = false
  }
}

async function onSaveConfig() {
  savingCfg.value = true
  try {
    await saveBackupConfig({
      backup_enabled: backupEnabled.value ? '1' : '0',
      backup_time: backupTime.value,
      backup_keep: String(backupKeep.value),
    })
    ui.toast('自动备份配置已保存', 'success')
  } catch (e) {
    ui.toast((e as Error).message, 'error')
  } finally {
    savingCfg.value = false
  }
}

onMounted(load)
</script>

<style scoped>
.module-title {
  font-size: 13px;
  color: var(--itsm-text-muted);
  margin: 4px 0 10px;
  display: flex;
  align-items: center;
  gap: 6px;
}
.stat-card {
  background: var(--itsm-card-bg);
  border: 1px solid var(--itsm-border);
  border-radius: 10px;
  padding: 14px;
  margin-bottom: 12px;
  text-align: center;
}
.stat-value {
  font-size: 22px;
  font-weight: 700;
  color: var(--el-color-primary);
}
.stat-label {
  font-size: 12px;
  color: var(--itsm-text-muted);
  margin-top: 2px;
}
.file-size-tip {
  font-size: 12px;
  color: var(--itsm-text-muted);
  margin: -2px 0 4px;
}
.op-card { height: 100%; }
.card-title { font-weight: 600; font-size: 14px; }
.danger-title { color: var(--el-color-danger); }
.mt-3 { margin-top: 12px; }
.mt-2 { margin-top: 8px; }
.header-actions { display: flex; align-items: center; gap: 8px; }
.w-full { width: 100%; }
.file-input { width: 100%; font-size: 13px; }
.inline-hint {
  font-size: 12px;
  color: var(--itsm-text-muted);
  margin-left: 8px;
}
.warn { font-size: 12px; color: var(--el-color-danger); margin-top: 2px; }
.field-hint {
  font-size: 12px;
  color: var(--itsm-text-muted);
  line-height: 1.5;
}
.kv-desc code {
  font-size: 12px;
  color: var(--el-color-primary);
  font-family: var(--font-mono, monospace);
  word-break: break-all;
}
</style>
