<template>
  <div class="page-container">
    <div class="page-header">
      <h2 class="page-title">固件版本库</h2>
      <div class="header-actions">
        <el-button v-if="user.hasPerm('device:edit')" type="primary" :icon="Plus" @click="openCreate()">
          新增固件版本
        </el-button>
      </div>
    </div>

    <!-- 筛选 -->
    <el-card shadow="never" class="filter-card">
      <div class="filter-row">
        <el-select v-model="filters.brand" placeholder="品牌" clearable filterable allow-create class="filter-item"
          @change="reload">
          <el-option v-for="b in data?.all_brands || []" :key="b" :label="b" :value="b" />
        </el-select>
        <el-select v-model="filters.model" placeholder="型号" clearable filterable allow-create class="filter-item"
          @change="reload">
          <el-option v-for="m in data?.all_models || []" :key="m" :label="m" :value="m" />
        </el-select>
        <el-select v-model="filters.firmware_type" placeholder="固件类型" clearable class="filter-item" @change="reload">
          <el-option v-for="t in data?.all_types || []" :key="t" :label="t" :value="t" />
        </el-select>
        <el-button type="primary" plain :icon="Search" @click="reload">查询</el-button>
      </div>
    </el-card>

    <!-- 分组列表 -->
    <el-card v-loading="loading" shadow="never">
      <div v-for="g in data?.groups || []" :key="g.brand + '|' + g.model" class="fw-group">
        <div class="fw-group-header">
          <span class="fw-brand">{{ g.brand || '未分类' }}</span>
          <span class="fw-model">{{ g.model || '未分类型号' }}</span>
          <el-tag v-if="g.devices.length" size="small" type="info">{{ g.devices.length }} 台在用设备</el-tag>
        </div>

        <div v-for="t in g.types" :key="t.firmware_type" class="fw-type">
          <div class="fw-type-title">{{ t.firmware_type }}</div>
          <DataTable
            :columns="firmwareColumns"
            :fetch-data="(params) => staticPage(t.items, params)"
            row-key="id"
            empty-text="暂无固件版本"
            :column-settings="{ storageKey: 'cols_firmwares' }"
          >
            <template #cell-version="{ row }">
              <span class="fw-version">{{ row.version }}</span>
              <el-tag v-if="row.is_latest" size="small" type="success" class="ml-2">最新</el-tag>
            </template>
          </DataTable>
        </div>

        <!-- 在用设备对比 -->
        <div v-if="g.devices.length" class="fw-devices">
          <div class="fw-type-title">在用设备版本</div>
          <el-table :data="g.devices" size="small" border>
            <el-table-column prop="name" :label="deviceLabel('device_name', '设备名称')" min-width="160" />
            <el-table-column prop="os_version" :label="deviceLabel('os_version', '系统版本')" min-width="140">
              <template #default="{ row }">{{ row.os_version || '-' }}</template>
            </el-table-column>
            <el-table-column prop="rule_version" :label="deviceLabel('rule_version', '规则库版本')" min-width="140">
              <template #default="{ row }">{{ row.rule_version || '-' }}</template>
            </el-table-column>
          </el-table>
        </div>
      </div>
      <el-empty v-if="!loading && !data?.groups?.length" description="暂无固件版本" :image-size="60" />
    </el-card>

    <!-- 新增/编辑 -->
    <el-dialog v-model="formVisible" :title="form.id ? '编辑固件版本' : '新增固件版本'" width="640px" destroy-on-close>
      <el-form ref="formRef" :model="form" label-width="110px">
        <el-row :gutter="12">
          <el-col :span="12">
            <el-form-item :label="label('brand', '品牌', 'form')" prop="brand" :rules="[{ required: true, message: '必填', trigger: 'blur' }]">
              <el-select v-model="form.brand" filterable allow-create clearable style="width: 100%">
                <el-option v-for="b in data?.all_brands || []" :key="b" :label="b" :value="b" />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item :label="label('model', '型号', 'form')" prop="model" :rules="[{ required: true, message: '必填', trigger: 'blur' }]">
              <el-select v-model="form.model" filterable allow-create clearable style="width: 100%">
                <el-option v-for="m in data?.all_models || []" :key="m" :label="m" :value="m" />
              </el-select>
            </el-form-item>
          </el-col>
        </el-row>
        <el-row :gutter="12">
          <el-col :span="12">
            <el-form-item :label="label('firmware_type', '固件类型', 'form')">
              <el-select v-model="form.firmware_type" style="width: 100%">
                <el-option v-for="t in data?.all_types || []" :key="t" :label="t" :value="t" />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item :label="label('version', '版本号', 'form')" prop="version" :rules="[{ required: true, message: '必填', trigger: 'blur' }]">
              <el-input v-model="form.version" placeholder="如 V2R20" />
            </el-form-item>
          </el-col>
        </el-row>
        <el-row :gutter="12">
          <el-col :span="12">
            <el-form-item :label="label('release_date', '发布日期', 'form')">
              <el-date-picker v-model="form.release_date" type="date" value-format="YYYY-MM-DD"
                style="width: 100%" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item :label="label('file_size_mb', '文件大小(MB)', 'form')">
              <el-input-number v-model="form.file_size_mb" :min="0" :precision="2" style="width: 100%" />
            </el-form-item>
          </el-col>
        </el-row>
        <el-form-item :label="label('is_latest', '最新版本', 'form')">
          <el-switch v-model="form.is_latest" active-text="标记为最新" />
          <div class="form-tip">同品牌+型号+类型仅一条最新</div>
        </el-form-item>
        <el-form-item :label="label('download_url', '下载地址', 'form')">
          <el-input v-model="form.download_url" placeholder="https://..." />
        </el-form-item>
        <el-form-item :label="label('md5_checksum', 'MD5 校验', 'form')">
          <el-input v-model="form.md5_checksum" placeholder="可选" />
        </el-form-item>
        <el-form-item :label="label('min_compatible_hardware', '最低硬件要求', 'form')">
          <el-input v-model="form.min_compatible_hardware" />
        </el-form-item>
        <el-form-item :label="label('changelog', '更新说明', 'form')">
          <el-input v-model="form.changelog" type="textarea" :rows="3" />
        </el-form-item>
        <el-form-item :label="label('upgrade_guide', '升级步骤', 'form')">
          <el-input v-model="form.upgrade_guide" type="textarea" :rows="3" />
        </el-form-item>
        <el-form-item :label="label('remark', '备注', 'form')">
          <el-input v-model="form.remark" type="textarea" :rows="2" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="formVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="save">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ElMessageBox } from 'element-plus/es/components/message-box/index'
import { ref, reactive, onMounted, computed } from 'vue'
import { Plus, Search } from '@element-plus/icons-vue'
import {
  fetchFirmwares, createFirmware, updateFirmware, deleteFirmware,
  type FirmwareListData, type FirmwareItem,
} from '@/api/firmwares'
import { useUserStore } from '@/stores/user'
import { useUiStore } from '@/stores/ui'
import { entityFieldLabel, fetchEntityMetas, type EntityMeta } from '@/api/meta'
import DataTable, { type DataColumn } from '@/components/DataTable.vue'

const user = useUserStore()
const ui = useUiStore()
const data = ref<FirmwareListData | null>(null)
const metas = ref<Record<string, EntityMeta>>({})
const loading = ref(false)
const filters = reactive<Record<string, string>>({ brand: '', model: '', firmware_type: '' })
const formVisible = ref(false)
const saving = ref(false)
const formRef = ref()
const form = reactive<Record<string, unknown>>({
  id: null, brand: '', model: '', firmware_type: '系统固件', version: '',
  release_date: '', changelog: '', download_url: '', file_size_mb: 0, md5_checksum: '',
  is_latest: false, min_compatible_hardware: '', upgrade_guide: '', remark: '',
})

function label(key: string, fallback: string, profile = 'list') {
  return entityFieldLabel(metas.value.firmware, key, fallback, profile)
}

function deviceLabel(key: string, fallback: string) {
  return entityFieldLabel(metas.value.device, key, fallback, 'list')
}

const firmwareColumns = computed<DataColumn[]>(() => [
  { key: 'version', label: label('version', '版本号'), width: 140, asTitle: true,
    ellipsis: false },
  { key: 'release_date', label: label('release_date', '发布日期'), width: 110, type: 'date' },
  { key: 'file_size_mb', label: label('file_size_mb', '文件大小(MB)'), width: 110 },
  { key: 'changelog', label: label('changelog', '更新说明'), minWidth: 180 },
  { key: 'actions', label: '操作', width: 140, type: 'action', fixed: 'right', actions: [
    { label: '编辑', type: 'primary', link: true, perm: 'device:edit',
      onClick: (row) => openEdit(row as unknown as FirmwareItem) },
    { label: '删除', type: 'danger', link: true, perm: 'device:delete',
      onClick: (row) => onDelete(row as unknown as FirmwareItem) },
  ] },
])

async function staticPage(rows: FirmwareItem[], params: Record<string, unknown>) {
  const page = Number(params.page) || 1
  const page_size = Number(params.page_size) || 20
  const start = (page - 1) * page_size
  return { items: rows.slice(start, start + page_size), total: rows.length, page, page_size }
}

function reload() {
  const params: Record<string, string> = {}
  for (const [k, v] of Object.entries(filters)) {
    if (v) params[k] = v
  }
  loading.value = true
  fetchFirmwares(params)
    .then((d) => { data.value = d })
    .catch(() => { /* toast */ })
    .finally(() => { loading.value = false })
}

function openCreate() {
  Object.assign(form, {
    id: null, brand: '', model: '', firmware_type: '系统固件', version: '',
    release_date: '', changelog: '', download_url: '', file_size_mb: 0, md5_checksum: '',
    is_latest: false, min_compatible_hardware: '', upgrade_guide: '', remark: '',
  })
  formVisible.value = true
}

function openEdit(row: FirmwareItem) {
  Object.assign(form, { ...row, id: row.id })
  formVisible.value = true
}

async function save() {
  try { await formRef.value?.validate() } catch { return }
  saving.value = true
  try {
    const payload = {
      brand: String(form.brand), model: String(form.model),
      firmware_type: String(form.firmware_type), version: String(form.version),
      release_date: String(form.release_date || ''),
      changelog: String(form.changelog || ''), download_url: String(form.download_url || ''),
      file_size_mb: Number(form.file_size_mb || 0), md5_checksum: String(form.md5_checksum || ''),
      is_latest: !!form.is_latest, min_compatible_hardware: String(form.min_compatible_hardware || ''),
      upgrade_guide: String(form.upgrade_guide || ''), remark: String(form.remark || ''),
    }
    if (form.id) {
      await updateFirmware(form.id as number, payload)
      ui.toast('已保存', 'success')
    } else {
      await createFirmware(payload)
      ui.toast('已添加', 'success')
    }
    formVisible.value = false
    reload()
  } catch (e) {
    ui.toast((e as Error).message, 'error')
  } finally {
    saving.value = false
  }
}

async function onDelete(row: FirmwareItem) {
  try {
    await ElMessageBox.confirm(`确定删除固件版本「${row.version}」吗？`, '删除确认', { type: 'warning' })
  } catch { return }
  try {
    await deleteFirmware(row.id)
    ui.toast('已删除', 'success')
    reload()
  } catch (e) {
    ui.toast((e as Error).message, 'error')
  }
}

onMounted(() => {
  reload()
  fetchEntityMetas(['firmware', 'device'])
    .then((result) => { metas.value = result })
    .catch(() => { /* 兼容滚动发布期间的旧后端 */ })
})
</script>

<style scoped>
.filter-card { margin-bottom: 12px; }
.filter-row { display: flex; gap: 8px; flex-wrap: wrap; }
.filter-item { width: 160px; }
.fw-group { border: 1px solid var(--itsm-border); border-radius: 8px; padding: 12px; margin-bottom: 12px; }
.fw-group-header { display: flex; align-items: center; gap: 10px; margin-bottom: 8px; }
.fw-brand { font-size: 15px; font-weight: 700; }
.fw-model { font-size: 13px; color: var(--itsm-text-muted); }
.fw-type { margin: 10px 0; }
.fw-type-title { font-size: 12px; font-weight: 600; color: var(--itsm-text-muted); margin-bottom: 6px; }
.fw-version { font-weight: 600; }
.fw-devices { margin-top: 10px; }
.ml-2 { margin-left: 6px; }
.form-tip { font-size: 12px; color: var(--itsm-text-muted); }
</style>
