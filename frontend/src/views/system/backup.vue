<template>
  <div class="page-container backup-page" v-loading="loading">
    <div class="page-header">
      <div>
        <h2 class="page-title">数据备份与恢复</h2>
        <p class="page-subtitle">集中管理 PostgreSQL 数据、系统配置、密钥和业务附件的备份。</p>
      </div>
      <el-tag :type="backupEnabled ? 'success' : 'warning'" effect="light">
        {{ backupEnabled ? `自动备份已启用 · 每日 ${backupTime}` : '自动备份未启用' }}
      </el-tag>
    </div>

    <div class="summary-grid">
      <div class="summary-item">
        <el-icon class="summary-icon"><FolderOpened /></el-icon>
        <div>
          <div class="summary-label">业务附件规模</div>
          <div class="summary-value">{{ fileSizeMb }} MB</div>
          <div class="summary-note">reports、uploads、static/uploads</div>
        </div>
      </div>
      <div class="summary-item">
        <el-icon class="summary-icon"><Clock /></el-icon>
        <div>
          <div class="summary-label">自动备份计划</div>
          <div class="summary-value">{{ backupEnabled ? `每日 ${backupTime}` : '未启用' }}</div>
          <div class="summary-note">由服务端调度器执行</div>
        </div>
      </div>
      <div class="summary-item">
        <el-icon class="summary-icon"><Files /></el-icon>
        <div>
          <div class="summary-label">保留策略</div>
          <div class="summary-value">最近 {{ backupKeep }} 份</div>
          <div class="summary-note">超出数量自动清理旧备份</div>
        </div>
      </div>
    </div>

    <el-row :gutter="14" class="main-grid">
      <el-col :xs="24" :lg="14">
        <el-card shadow="never" class="section-card">
          <template #header>
            <div class="section-header">
              <div>
                <span class="card-title">导出备份</span>
                <span class="card-description">立即生成并下载可恢复的备份包</span>
              </div>
              <el-tag size="small" type="info">ZIP</el-tag>
            </div>
          </template>

          <el-form label-position="top" @submit.prevent>
            <el-form-item label="备份范围">
              <el-radio-group v-model="exportConfigOnly" class="scope-group">
                <el-radio-button :value="false">全量备份</el-radio-button>
                <el-radio-button :value="true">仅配置</el-radio-button>
              </el-radio-group>
            </el-form-item>

            <div class="scope-detail">
              <div class="scope-title">
                {{ exportConfigOnly ? '仅配置备份包含' : '全量备份包含' }}
              </div>
              <div class="scope-tags">
                <el-tag v-for="item in exportScope" :key="item" size="small" effect="plain">{{ item }}</el-tag>
              </div>
              <div v-if="!exportConfigOnly" class="scope-hint">
                业务附件约 {{ fileSizeMb }} MB，实际备份包还包含数据库和配置文件。
              </div>
            </div>

            <el-form-item label="备份包密码（可选）">
              <el-input
                v-model="exportPassword"
                type="password"
                show-password
                autocomplete="new-password"
                placeholder="设置后，恢复时必须输入相同密码"
              />
            </el-form-item>

            <el-button type="primary" :icon="Download" :loading="exporting" @click="onExport">
              生成并下载备份包
            </el-button>
          </el-form>
        </el-card>
      </el-col>

      <el-col :xs="24" :lg="10">
        <el-card shadow="never" class="section-card">
          <template #header>
            <div class="section-header">
              <div>
                <span class="card-title">自动备份</span>
                <span class="card-description">设置每日执行时间和本地保留数量</span>
              </div>
              <el-switch v-model="backupEnabled" inline-prompt active-text="开" inactive-text="关" />
            </div>
          </template>

          <el-form label-position="top" @submit.prevent>
            <el-row :gutter="12">
              <el-col :xs="24" :sm="12">
                <el-form-item label="每日执行时间">
                  <el-time-select
                    v-model="backupTime"
                    start="00:00"
                    step="00:30"
                    end="23:30"
                    placeholder="03:00"
                    class="w-full"
                    :disabled="!backupEnabled"
                  />
                </el-form-item>
              </el-col>
              <el-col :xs="24" :sm="12">
                <el-form-item label="保留份数">
                  <el-input-number
                    v-model="backupKeep"
                    :min="1"
                    :max="365"
                    controls-position="right"
                    class="w-full"
                  />
                </el-form-item>
              </el-col>
            </el-row>

            <el-alert
              type="info"
              :closable="false"
              show-icon
              :title="backupEnabled ? `系统将在每日 ${backupTime} 自动备份` : '启用后才会按计划自动备份'"
              class="schedule-alert"
            />
            <el-button type="primary" plain :loading="savingCfg" @click="onSaveConfig">
              保存自动备份设置
            </el-button>
          </el-form>
        </el-card>
      </el-col>
    </el-row>

    <el-card shadow="never" class="section-card restore-card">
      <template #header>
        <div class="section-header">
          <div>
            <span class="card-title danger-title">从备份包恢复</span>
            <span class="card-description">覆盖恢复仅用于迁移、灾难恢复或明确的数据回退</span>
          </div>
          <el-tag size="small" type="danger" effect="dark">高风险操作</el-tag>
        </div>
      </template>

      <el-alert
        type="error"
        :closable="false"
        show-icon
        title="恢复会清空并覆盖当前数据。执行前系统会自动生成 pre_import_*.zip 作为回退点。"
      />

      <el-form label-position="top" class="restore-form" @submit.prevent>
        <el-row :gutter="14">
          <el-col :xs="24" :md="8">
            <el-form-item label="备份文件">
              <input ref="fileInput" type="file" accept=".zip" class="file-input" />
              <span class="field-hint">仅支持由本系统生成的 .zip 备份包</span>
            </el-form-item>
          </el-col>
          <el-col :xs="24" :md="6">
            <el-form-item label="备份包密码">
              <el-input
                v-model="importPassword"
                type="password"
                show-password
                autocomplete="new-password"
                placeholder="未加密则留空"
              />
            </el-form-item>
          </el-col>
          <el-col :xs="24" :md="5">
            <el-form-item label="密钥处理">
              <el-checkbox v-model="restoreKey">同时恢复 .secret.key</el-checkbox>
              <span class="field-hint">跨环境迁移密文时通常需要</span>
            </el-form-item>
          </el-col>
          <el-col :xs="24" :md="5">
            <el-form-item label="二次确认">
              <el-input v-model="confirmText" placeholder="输入：我确认覆盖" />
            </el-form-item>
          </el-col>
        </el-row>
        <div class="restore-actions">
          <span class="field-hint">只有确认文字完全一致后才能执行恢复。</span>
          <el-button
            type="danger"
            :disabled="confirmText !== '我确认覆盖'"
            :loading="importing"
            @click="onImport"
          >
            执行覆盖恢复
          </el-button>
        </div>
      </el-form>
    </el-card>

    <el-collapse v-model="infoOpen" class="operation-guide">
      <el-collapse-item name="info" title="运维恢复说明与命令">
        <el-descriptions :column="2" size="small" border>
          <el-descriptions-item label="PostgreSQL 数据库"><code>itsm_pg_&lt;时间戳&gt;.dump</code></el-descriptions-item>
          <el-descriptions-item label="密钥与文件"><code>itsm_meta_&lt;时间戳&gt;.tar.gz</code></el-descriptions-item>
          <el-descriptions-item label="导入前回退包"><code>pre_import_&lt;时间戳&gt;.zip</code></el-descriptions-item>
          <el-descriptions-item label="整机恢复"><code>scripts/restore.sh &lt;目录&gt; &lt;备份&gt;</code></el-descriptions-item>
          <el-descriptions-item label="紧急回滚"><code>scripts/rollback.sh &lt;目录&gt; &lt;备份&gt;</code></el-descriptions-item>
          <el-descriptions-item label="关键要求">数据库与 .secret.key 必须成对保存</el-descriptions-item>
        </el-descriptions>
      </el-collapse-item>
    </el-collapse>
  </div>
</template>

<script setup lang="ts">
import { ElMessageBox } from 'element-plus/es/components/message-box/index'
import { computed, onMounted, ref } from 'vue'
import { Clock, Download, Files, FolderOpened } from '@element-plus/icons-vue'
import { exportBackup, fetchBackupConfig, fetchBackupStats, importBackup, saveBackupConfig } from '@/api/system'
import { useUiStore } from '@/stores/ui'

const ui = useUiStore()
const loading = ref(false)
const fileSizeMb = ref('0')
const infoOpen = ref<string[]>([])

const exportConfigOnly = ref(false)
const exportPassword = ref('')
const exporting = ref(false)

const fileInput = ref<HTMLInputElement>()
const restoreKey = ref(false)
const importPassword = ref('')
const confirmText = ref('')
const importing = ref(false)

const backupEnabled = ref(false)
const backupTime = ref('03:00')
const backupKeep = ref(30)
const savingCfg = ref(false)

const exportScope = computed(() => exportConfigOnly.value
  ? ['系统配置', '加密密钥']
  : ['PostgreSQL 数据', '系统配置', '加密密钥', '业务附件'])

async function load() {
  loading.value = true
  try {
    const [stats, config] = await Promise.all([fetchBackupStats(), fetchBackupConfig()])
    fileSizeMb.value = String(stats.file_size_mb)
    backupEnabled.value = config.backup_enabled === '1'
    backupTime.value = config.backup_time || '03:00'
    backupKeep.value = Number(config.backup_keep) || 30
  } catch (error) {
    ui.toast((error as Error).message, 'error')
  } finally {
    loading.value = false
  }
}

function downloadByToken(token: string, filename: string) {
  const anchor = document.createElement('a')
  anchor.href = `/api/system/backup/export-download/${token}`
  anchor.download = filename
  document.body.appendChild(anchor)
  anchor.click()
  anchor.remove()
}

async function onExport() {
  try {
    await ElMessageBox.confirm(
      `确定生成${exportConfigOnly.value ? '仅配置' : '全量'}备份包吗？`,
      '导出确认',
      { type: 'info', confirmButtonText: '生成备份' },
    )
  } catch { return }

  exporting.value = true
  try {
    const result = await exportBackup({
      config_only: exportConfigOnly.value,
      password: exportPassword.value || undefined,
    })
    downloadByToken(result.token, result.filename)
    ui.toast('备份包已生成，请保存下载文件', 'success')
  } catch (error) {
    ui.toast((error as Error).message, 'error')
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
    await ElMessageBox.confirm(
      '导入将清空并覆盖全部现有数据。系统会先生成回退备份，确定继续吗？',
      '确认覆盖恢复',
      { type: 'warning', confirmButtonText: '继续恢复' },
    )
  } catch { return }

  importing.value = true
  try {
    const formData = new FormData()
    formData.append('backup_file', file)
    formData.append('confirm', confirmText.value)
    formData.append('restore_secret_key', restoreKey.value ? '1' : '0')
    if (importPassword.value) formData.append('password', importPassword.value)
    const result = await importBackup(formData)
    const preImport = result.pre_import_file ? `；回退备份：${result.pre_import_file}` : ''
    ui.toast(`${result.message}${preImport}`, 'success')
    confirmText.value = ''
    await load()
  } catch (error) {
    ui.toast((error as Error).message, 'error')
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
    ui.toast('自动备份设置已保存', 'success')
  } catch (error) {
    ui.toast((error as Error).message, 'error')
  } finally {
    savingCfg.value = false
  }
}

onMounted(load)
</script>

<style scoped>
.backup-page { max-width: 1500px; margin: 0 auto; }
.summary-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 12px; }
.summary-item {
  display: flex; align-items: center; gap: 12px; min-width: 0; padding: 15px 16px;
  background: var(--itsm-card-bg); border: 1px solid var(--itsm-border); border-radius: 10px;
}
.summary-icon { flex: 0 0 auto; padding: 10px; color: var(--el-color-primary); font-size: 22px; background: var(--el-color-primary-light-9); border-radius: 9px; }
.summary-label { color: var(--itsm-text-muted); font-size: 12px; }
.summary-value { margin-top: 2px; font-size: 17px; font-weight: 650; }
.summary-note { margin-top: 2px; overflow: hidden; color: var(--itsm-text-muted); font-size: 11px; text-overflow: ellipsis; white-space: nowrap; }
.main-grid { margin-top: 14px; }
.section-card { height: calc(100% - 14px); margin-bottom: 14px; }
.section-header { display: flex; justify-content: space-between; align-items: center; gap: 14px; }
.card-title { font-size: 15px; font-weight: 650; }
.card-description { margin-left: 12px; color: var(--itsm-text-muted); font-size: 12px; }
.danger-title { color: var(--el-color-danger); }
.scope-group { width: 100%; }
.scope-group :deep(.el-radio-button) { flex: 1; }
.scope-group :deep(.el-radio-button__inner) { width: 100%; }
.scope-detail { margin: -4px 0 16px; padding: 13px 14px; background: var(--el-fill-color-lighter); border-radius: 8px; }
.scope-title { margin-bottom: 8px; font-size: 12px; font-weight: 600; }
.scope-tags { display: flex; gap: 6px; flex-wrap: wrap; }
.scope-hint { margin-top: 8px; color: var(--itsm-text-muted); font-size: 11px; }
.schedule-alert { margin-bottom: 16px; }
.w-full { width: 100%; }
.restore-card { height: auto; }
.restore-form { margin-top: 16px; }
.restore-actions { display: flex; justify-content: flex-end; align-items: center; gap: 14px; padding-top: 2px; border-top: 1px solid var(--itsm-border); }
.file-input {
  box-sizing: border-box; width: 100%; min-height: 32px; padding: 5px 8px;
  color: var(--itsm-text); font-size: 12px; border: 1px solid var(--itsm-border); border-radius: 5px;
}
.field-hint { display: block; margin-top: 5px; color: var(--itsm-text-muted); font-size: 11px; line-height: 1.4; }
.operation-guide { margin-top: 2px; }
.operation-guide code { color: var(--el-color-primary); font-family: var(--font-mono, monospace); font-size: 12px; }
@media (max-width: 900px) {
  .summary-grid { grid-template-columns: 1fr; }
  .card-description { display: block; margin: 4px 0 0; }
  .restore-actions { align-items: stretch; flex-direction: column; }
}
</style>
