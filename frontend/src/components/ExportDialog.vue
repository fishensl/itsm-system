<template>
  <el-dialog :model-value="modelValue" :title="dialogTitle" width="620px" top="6vh"
    destroy-on-close @update:model-value="(v: boolean) => emit('update:modelValue', v)">
    <div class="export-dialog">
      <!-- 设备模块：三类预设 -->
      <div v-if="module === 'device'" class="preset-row">
        <el-radio-group v-model="preset" @change="onPresetChange">
          <el-radio-button v-for="p in devicePresets" :key="p.key" :value="p.key">
            {{ p.label }}
          </el-radio-button>
        </el-radio-group>
      </div>

      <!-- bundle 模式：项目勾选 -->
      <template v-if="mode === 'bundle'">
        <div class="section-title">导出项目（至少勾选一项）</div>
        <el-checkbox-group v-model="items">
          <el-checkbox v-for="it in bundleItems" :key="it.key" :value="it.key">{{ it.label }}</el-checkbox>
        </el-checkbox-group>
      </template>

      <!-- excel 模式：列选择 -->
      <template v-else>
        <div class="section-title">
          导出列
          <span class="col-actions">
            <el-link type="primary" :underline="false" @click="selectAll">全选</el-link>
            <el-link type="info" :underline="false" @click="resetCols">重置</el-link>
          </span>
        </div>
        <el-checkbox-group v-model="selectedCols" class="col-grid">
          <el-checkbox v-for="c in allColumns" :key="c.key" :value="c.key" class="col-item"
            :class="{ 'col-pwd': c.key === 'password' }">
            {{ c.label }}
          </el-checkbox>
        </el-checkbox-group>
      </template>

      <!-- 客户多选 -->
      <template v-if="hasCustomerFilter">
        <div class="section-title">客户（不选 = 全部）</div>
        <el-select v-model="customerIds" multiple filterable collapse-tags clearable class="w-full"
          placeholder="多选客户，留空导出全部">
          <el-option v-for="c in customerOptions" :key="c.id" :label="c.name" :value="c.id" />
        </el-select>
      </template>

      <!-- 日期范围 -->
      <template v-if="hasDateFilter">
        <div class="section-title">{{ dateLabel }}范围（不选 = 全部）</div>
        <el-date-picker v-model="dateRange" type="daterange" value-format="YYYY-MM-DD"
          start-placeholder="开始日期" end-placeholder="结束日期" class="w-full" />
      </template>

      <!-- 密码审核流 -->
      <div v-if="hasPassword && mode !== 'bundle'" class="pwd-flow">
        <el-alert v-if="hasPasswordColumn" type="warning" :closable="false" show-icon
          title="已勾选「登录密码」：导出将转入审核流程（管理员通过后下载加密包），请填写申请原因" />
        <el-input v-if="hasPasswordColumn" v-model="reason" type="textarea" :rows="2"
          maxlength="500" show-word-limit placeholder="申请原因（必填）：如 等保审计需要导出设备密码台账" />
      </div>
    </div>
    <template #footer>
      <el-button @click="emit('update:modelValue', false)">取消</el-button>
      <el-button type="primary" :loading="submitting" @click="doSubmit">
        {{ hasPasswordColumn ? '提交导出申请' : '导出' }}
      </el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { ElMessage } from 'element-plus'
import {
  DEVICE_EXPORT_COLUMNS, DEVICE_PRESETS,
  INSPECTION_EXPORT_COLUMNS, TICKET_EXPORT_COLUMNS, FAULT_EXPORT_COLUMNS,
  SPARE_EXPORT_COLUMNS, CUSTOMER_EXPORT_COLUMNS,
  INSPECTION_BUNDLE_ITEMS, TICKET_BUNDLE_ITEMS,
  type ExportColumn,
} from '@/utils/exportColumns'
import { fetchCustomers } from '@/api/customers'

const props = defineProps<{
  modelValue: boolean
  module: 'device' | 'inspection' | 'ticket' | 'fault' | 'customer' | 'spare'
  mode?: 'excel' | 'bundle'
  title?: string
  /** 打开时预选的客户（如设备页当前查看的客户）；不传则默认不选=全部 */
  defaultCustomerIds?: number[]
}>()
const emit = defineEmits<{
  (e: 'update:modelValue', v: boolean): void
  (e: 'submit', payload: Record<string, unknown>): void
}>()

const devicePresets = DEVICE_PRESETS
const allColumns = computed<ExportColumn[]>(() => {
  const map: Record<string, ExportColumn[]> = {
    device: DEVICE_EXPORT_COLUMNS, inspection: INSPECTION_EXPORT_COLUMNS,
    ticket: TICKET_EXPORT_COLUMNS, fault: FAULT_EXPORT_COLUMNS,
    spare: SPARE_EXPORT_COLUMNS, customer: CUSTOMER_EXPORT_COLUMNS,
  }
  return map[props.module] || []
})

const bundleItems = computed(() => props.module === 'inspection'
  ? INSPECTION_BUNDLE_ITEMS
  : props.module === 'ticket' ? TICKET_BUNDLE_ITEMS : [])

const dialogTitle = computed(() => props.title || (
  props.mode === 'bundle'
    ? (props.module === 'inspection' ? '导出巡检资料包' : '导出工单报告包')
    : '导出'))

const hasCustomerFilter = computed(() =>
  ['device', 'inspection', 'ticket', 'fault'].includes(props.module))
const hasDateFilter = computed(() =>
  ['inspection', 'ticket', 'fault', 'customer', 'spare'].includes(props.module))
const hasPassword = computed(() => props.module === 'device')

const dateLabel = computed(() => {
  const map: Record<string, string> = {
    inspection: '巡检日期', ticket: '创建时间', fault: '故障时间',
    customer: '创建时间', spare: '创建时间', device: '时间',
  }
  return map[props.module] || '时间'
})

const preset = ref('asset')
const selectedCols = ref<string[]>([])
const items = ref<string[]>([])
const customerIds = ref<number[]>([])
const dateRange = ref<[string, string] | null>(null)
const reason = ref('')
const submitting = ref(false)
const customerOptions = ref<{ id: number; name: string }[]>([])

const storageKey = computed(() => `export_cols_${props.module}`)
const presetKey = computed(() => `export_preset_${props.module}`)
const hasPasswordColumn = computed(() => selectedCols.value.includes('password'))

function selectAll() {
  selectedCols.value = allColumns.value.map((c) => c.key)
}

function resetCols() {
  const key = props.module === 'device' ? preset.value : ''
  if (key && props.module === 'device') {
    const p = devicePresets.find((x) => x.key === key)
    selectedCols.value = p ? [...p.columns] : allColumns.value.map((c) => c.key)
  } else {
    selectedCols.value = allColumns.value.map((c) => c.key)
  }
}

/** 打开时恢复上次选择：预设 + 列；无记录则按预设默认列载入 */
function loadSaved() {
  const saved = localStorage.getItem(storageKey.value)
  if (saved) {
    try {
      const arr = JSON.parse(saved) as string[]
      selectedCols.value = arr.filter((k) => allColumns.value.some((c) => c.key === k))
    } catch { selectedCols.value = [] }
  }
  if (props.module === 'device') {
    const p = localStorage.getItem(presetKey.value)
    if (p && devicePresets.some((x) => x.key === p)) preset.value = p
  }
  if (!selectedCols.value.length) resetCols()
}

/** 切换预设 → 自动勾选该预设的默认列集合（可再增删） */
function onPresetChange(key: string) {
  const p = devicePresets.find((x) => x.key === key)
  if (p) {
    selectedCols.value = [...p.columns]
    localStorage.setItem(presetKey.value, key)
  }
}

function loadCustomers() {
  fetchCustomers({ page: 1, page_size: 1000 })
    .then((d) => { customerOptions.value = d.items.map((c) => ({ id: c.id, name: c.name })) })
    .catch(() => { /* toast */ })
}

watch(
  () => props.modelValue,
  (v) => {
    if (!v) return
    loadSaved()
    items.value = bundleItems.value.map((i) => i.key)
    customerIds.value = props.defaultCustomerIds?.length ? [...props.defaultCustomerIds] : []
    dateRange.value = null
    reason.value = ''
    if (hasCustomerFilter.value && !customerOptions.value.length) loadCustomers()
  },
  { immediate: true },
)

watch(
  () => selectedCols.value,
  (cols) => {
    if (cols.length) localStorage.setItem(storageKey.value, JSON.stringify(cols))
  },
  { deep: true },
)

function doSubmit() {
  if (props.mode === 'bundle') {
    if (!items.value.length) {
      ElMessage.warning('请至少勾选一个导出项目')
      return
    }
    emit('submit', {
      items: items.value,
      customer_ids: customerIds.value,
      date_from: dateRange.value?.[0] || '',
      date_to: dateRange.value?.[1] || '',
    })
    return
  }
  if (!selectedCols.value.length) {
    ElMessage.warning('请至少勾选一列')
    return
  }
  if (hasPasswordColumn.value && !reason.value.trim()) {
    ElMessage.warning('勾选「登录密码」时申请原因必填')
    return
  }
  const payload: Record<string, unknown> = {
    columns: selectedCols.value,
    customer_ids: customerIds.value,
    date_from: dateRange.value?.[0] || '',
    date_to: dateRange.value?.[1] || '',
  }
  if (props.module === 'device') {
    payload.preset = preset.value
    payload.reason = reason.value.trim()
    payload.has_password = hasPasswordColumn.value
  }
  emit('submit', payload)
}
</script>

<style scoped>
.export-dialog { display: flex; flex-direction: column; gap: 14px; }
.preset-row { display: flex; flex-wrap: wrap; gap: 8px; }
.section-title { font-size: 13px; font-weight: 600; color: var(--el-text-color-primary); }
.col-actions { float: right; font-weight: 400; display: inline-flex; gap: 10px; }
.col-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 6px 10px; max-height: 220px; overflow: auto; width: 100%; }
.col-item { margin-right: 0; }
.col-pwd :deep(.el-checkbox__label) { color: var(--el-color-danger); font-weight: 600; }
.pwd-flow { display: flex; flex-direction: column; gap: 8px; }
.w-full { width: 100%; }
</style>
