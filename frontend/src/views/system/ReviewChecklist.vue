<template>
  <div class="page-container">
    <div class="page-header">
      <h2 class="page-title">巡检审核清单</h2>
      <div class="header-actions">
        <el-button :icon="Plus" plain @click="addItem">添加检查项</el-button>
        <el-button type="primary" :icon="Check" :loading="saving" @click="save">保存</el-button>
      </div>
    </div>

    <el-card shadow="never">
      <div class="tips">
        审核人打开巡检审核弹窗时逐项核对（合格 / 需修改 / 不适用），勾选结果随每轮审核留痕；
        退回时「需修改」项自动生成修改要求，工程师据此修改重传。
      </div>
      <DataTable
        ref="tableRef"
        :columns="columns"
        :fetch-data="fetchPage"
        row-key="_key"
        empty-text="暂无审核检查项"
        :column-settings="{ storageKey: 'cols_review_checklist' }"
      >
        <template #cell-sort_order="{ row }">{{ itemPosition(row) }}</template>
        <template #cell-name="{ row }">
          <el-input v-model="row.name" size="small" placeholder="如：核心设备配置备份" />
        </template>
        <template #cell-enabled="{ row }">
          <el-switch v-model="row.enabled" />
        </template>
      </DataTable>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { Plus, Check } from '@element-plus/icons-vue'
import { useUiStore } from '@/stores/ui'
import { fetchReviewChecklist, updateReviewChecklist, type ReviewChecklistItem } from '@/api/inspections'
import { entityFieldLabel, fetchEntityMeta, type EntityMeta } from '@/api/meta'
import DataTable, { type DataColumn } from '@/components/DataTable.vue'

const ui = useUiStore()
type EditableChecklistItem = ReviewChecklistItem & { _key: number }

const items = ref<EditableChecklistItem[]>([])
const metadata = ref<EntityMeta>()
const saving = ref(false)
const tableRef = ref()
let loaded = false
let nextKey = 0

function label(key: string, fallback: string) {
  return entityFieldLabel(metadata.value, key, fallback, 'list')
}

function itemPosition(row: Record<string, unknown>) {
  return items.value.indexOf(row as unknown as EditableChecklistItem) + 1
}

function addItem() {
  items.value.push({ name: '', enabled: true, _key: ++nextKey })
  tableRef.value?.refresh()
}

function removeItem(i: number) {
  items.value.splice(i, 1)
  tableRef.value?.refresh()
}

function move(i: number, dir: number) {
  const j = i + dir
  if (j < 0 || j >= items.value.length) return
  const tmp = items.value[i]
  items.value[i] = items.value[j]
  items.value[j] = tmp
  tableRef.value?.refresh()
}

const columns = computed<DataColumn[]>(() => [
  { key: 'sort_order', label: label('sort_order', '顺序'), width: 70, align: 'center' },
  { key: 'name', label: label('name', '检查项名称'), minWidth: 220, asTitle: true,
    ellipsis: false },
  { key: 'enabled', label: label('enabled', '启用'), width: 90, align: 'center' },
  { key: 'actions', label: '操作', width: 180, type: 'action', fixed: 'right', actions: [
    { icon: 'ArrowUp', type: 'primary', link: true,
      disabled: (row) => items.value.indexOf(row as unknown as EditableChecklistItem) === 0,
      onClick: (row) => move(items.value.indexOf(row as unknown as EditableChecklistItem), -1) },
    { icon: 'ArrowDown', type: 'primary', link: true,
      disabled: (row) => items.value.indexOf(row as unknown as EditableChecklistItem) === items.value.length - 1,
      onClick: (row) => move(items.value.indexOf(row as unknown as EditableChecklistItem), 1) },
    { icon: 'Delete', type: 'danger', link: true,
      onClick: (row) => removeItem(items.value.indexOf(row as unknown as EditableChecklistItem)) },
  ] },
])

async function fetchPage(params: Record<string, unknown>) {
  if (!loaded) {
    const [result, meta] = await Promise.all([
      fetchReviewChecklist(), fetchEntityMeta('review_checklist_config'),
    ])
    metadata.value = meta
    items.value = result.items.map((item) => ({ ...item, _key: ++nextKey }))
    loaded = true
  }
  const page = Number(params.page) || 1
  const page_size = Number(params.page_size) || 20
  const start = (page - 1) * page_size
  return { items: items.value.slice(start, start + page_size), total: items.value.length,
    page, page_size }
}

async function save() {
  const cleaned = items.value
    .map((it) => ({ name: (it.name || '').trim(), enabled: it.enabled }))
    .filter((it) => it.name)
  if (!cleaned.length) {
    ui.toast('至少保留一个检查项', 'warning')
    return
  }
  saving.value = true
  try {
    await updateReviewChecklist(cleaned)
    items.value = cleaned.map((item) => ({ ...item, _key: ++nextKey }))
    ui.toast('已保存', 'success')
    tableRef.value?.refresh()
  } catch (e) {
    ui.toast((e as Error).message, 'error')
  } finally {
    saving.value = false
  }
}

</script>

<style scoped>
.page-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; }
.header-actions { display: flex; gap: 8px; }
.tips {
  font-size: 12px; color: var(--itsm-text-muted); background: var(--el-color-primary-light-9);
  border: 1px solid var(--el-color-primary-light-5); border-radius: 6px; padding: 8px 12px; margin-bottom: 12px;
}
</style>
