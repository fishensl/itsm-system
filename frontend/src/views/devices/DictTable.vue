<template>
  <div>
    <div class="tab-toolbar">
      <el-button v-if="user.hasPerm('device:edit')" @click="openSort">拖动排序</el-button>
      <el-button v-if="user.hasPerm('device:edit')" type="primary" :icon="Plus" @click="openCreate">
        新增
      </el-button>
    </div>

    <DataTable
      ref="tableRef"
      :columns="columns"
      :fetch-data="fetchPage"
      row-key="id"
      empty-text="暂无数据"
      :column-settings="{ storageKey: `cols_device_dict_${resource}` }"
    />

    <el-dialog v-model="sortVisible" title="拖动排序" width="460px">
      <div class="sort-hint">按住左侧手柄拖动，保存后立即生效。</div>
      <div class="sort-list">
        <div v-for="(item, index) in sortItems" :key="item.id" class="sort-item"
          draggable="true" @dragstart="dragIndex = index" @dragover.prevent @drop="dropSort(index)">
          <span class="drag-handle">☰</span><span>{{ item.name }}</span>
          <el-tag v-if="item.is_active === false" size="small" type="info">已停用</el-tag>
          <span class="sort-actions">
            <el-button size="small" link :disabled="index === 0" @click="moveSort(index, -1)">上移</el-button>
            <el-button size="small" link :disabled="index === sortItems.length - 1"
              @click="moveSort(index, 1)">下移</el-button>
          </span>
        </div>
      </div>
      <template #footer>
        <el-button @click="sortVisible = false">取消</el-button>
        <el-button type="primary" :loading="sortSaving" @click="saveSort">保存排序</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="formVisible" :title="form.id ? '编辑' : '新增'" width="420px" destroy-on-close>
      <el-form ref="formRef" :model="form" label-width="80px">
        <el-form-item :label="label('name', '名称', 'form')" prop="name" :rules="[{ required: true, message: '请输入名称', trigger: 'blur' }]">
          <el-input v-model="form.name" placeholder="名称" />
        </el-form-item>
        <el-form-item v-if="showType" :label="label('field_type', '字段类型', 'form')">
          <el-select v-model="form.field_type" style="width: 100%">
            <el-option v-for="(optionLabel, value) in FIELD_TYPE_OPTIONS" :key="value"
              :label="optionLabel" :value="value" />
          </el-select>
        </el-form-item>
        <el-form-item v-if="showActive" label="启用">
          <el-switch v-model="form.is_active" />
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
import { Plus } from '@element-plus/icons-vue'
import {
  fetchDeviceDict, createDeviceDict, updateDeviceDict, deleteDeviceDict, reorderDeviceDict,
  type DictItem, type Resource,
} from '@/api/deviceDicts'
import { useUserStore } from '@/stores/user'
import { useUiStore } from '@/stores/ui'
import { entityFieldLabel, fetchEntityMeta, type EntityMeta } from '@/api/meta'
import DataTable, { type DataColumn } from '@/components/DataTable.vue'

const props = withDefaults(defineProps<{
  resource: Resource
  showType: boolean
  showActive?: boolean
}>(), { showActive: false })

/** 自定义字段类型（对齐后端 utils/permission.py FIELD_TYPE_CHOICES） */
const FIELD_TYPE_OPTIONS: Record<string, string> = {
  text: '单行文本',
  multiline_text: '多行文本',
  dropdown: '下拉选择',
  number: '数字',
  image: '图片上传',
  date: '日期',
}
const FIELD_TYPE_LABELS = FIELD_TYPE_OPTIONS

const user = useUserStore()
const ui = useUiStore()
const metadata = ref<EntityMeta>()
const tableRef = ref()
const formVisible = ref(false)
const saving = ref(false)
const formRef = ref()
const form = reactive<Record<string, unknown>>({
  id: null, name: '', field_type: 'text', is_active: true,
})
const sortVisible = ref(false)
const sortSaving = ref(false)
const sortItems = ref<DictItem[]>([])
const dragIndex = ref<number | null>(null)

function label(key: string, fallback: string, profile = 'list') {
  return entityFieldLabel(metadata.value, key, fallback, profile)
}

const columns = computed<DataColumn[]>(() => {
  const result: DataColumn[] = [
    { key: 'name', label: label('name', '名称'), minWidth: 200, asTitle: true },
  ]
  if (props.showType) {
    result.push({
      key: 'field_type', label: label('field_type', '字段类型'), width: 120,
      type: 'tag', valueMap: FIELD_TYPE_LABELS,
      tagMap: { date: 'warning' },
    })
  }
  if (props.showActive) {
    result.push({ key: 'is_active', label: '状态', width: 90, type: 'tag',
      valueMap: { 'true': '启用', 'false': '停用' },
      tagMap: { 'true': 'success', 'false': 'info' } })
  }
  result.push(
    { key: 'sort_order', label: label('sort_order', '排序'), width: 80 },
    { key: 'actions', label: '操作', width: 150, type: 'action', fixed: 'right', actions: [
      { label: '编辑', type: 'primary', link: true, perm: 'device:edit',
        onClick: (row) => openEdit(row as unknown as DictItem) },
      { label: '删除', type: 'danger', link: true, perm: 'device:delete',
        onClick: (row) => onDelete(row as unknown as DictItem) },
    ] },
  )
  return result
})

async function fetchPage(params: Record<string, unknown>) {
  const list = await fetchDeviceDict(props.resource)
  const page = Number(params.page) || 1
  const page_size = Number(params.page_size) || 20
  const start = (page - 1) * page_size
  return { items: list.slice(start, start + page_size), total: list.length, page, page_size }
}

function load() {
  tableRef.value?.refresh()
}

function openCreate() {
  Object.assign(form, { id: null, name: '', field_type: 'text', is_active: true })
  formVisible.value = true
}

function openEdit(row: DictItem) {
  Object.assign(form, { id: row.id, name: row.name,
    field_type: row.field_type || 'text', is_active: row.is_active !== false })
  formVisible.value = true
}

async function save() {
  try { await formRef.value?.validate() } catch { return }
  saving.value = true
  try {
    const payload = { name: String(form.name) }
    if (props.showType) Object.assign(payload, { field_type: String(form.field_type || 'text') })
    if (props.showActive) Object.assign(payload, { is_active: Boolean(form.is_active) })
    if (form.id) {
      await updateDeviceDict(props.resource, form.id as number, payload)
      ui.toast('已保存', 'success')
    } else {
      await createDeviceDict(props.resource, payload)
      ui.toast('已添加', 'success')
    }
    formVisible.value = false
    load()
  } catch (e) {
    ui.toast((e as Error).message, 'error')
  } finally {
    saving.value = false
  }
}

async function openSort() {
  try {
    sortItems.value = [...await fetchDeviceDict(props.resource)]
    sortVisible.value = true
  } catch (e) {
    ui.toast((e as Error).message, 'error')
  }
}

function dropSort(targetIndex: number) {
  if (dragIndex.value == null || dragIndex.value === targetIndex) return
  const next = [...sortItems.value]
  const [moved] = next.splice(dragIndex.value, 1)
  next.splice(targetIndex, 0, moved)
  sortItems.value = next
  dragIndex.value = null
}

function moveSort(index: number, delta: number) {
  const target = index + delta
  if (target < 0 || target >= sortItems.value.length) return
  const next = [...sortItems.value]
  ;[next[index], next[target]] = [next[target], next[index]]
  sortItems.value = next
}

async function saveSort() {
  sortSaving.value = true
  try {
    await reorderDeviceDict(props.resource, sortItems.value.map((item) => item.id))
    ui.toast('排序已保存', 'success')
    sortVisible.value = false
    load()
  } catch (e) {
    ui.toast((e as Error).message, 'error')
  } finally {
    sortSaving.value = false
  }
}

async function onDelete(row: DictItem) {
  try {
    await ElMessageBox.confirm(`确定删除「${row.name}」吗？`, '删除确认', { type: 'warning' })
  } catch { return }
  try {
    await deleteDeviceDict(props.resource, row.id)
    ui.toast('已删除', 'success')
    load()
  } catch (e) {
    ui.toast((e as Error).message, 'error')
  }
}

onMounted(() => {
  fetchEntityMeta('device_dictionary')
    .then((result) => { metadata.value = result })
    .catch(() => { /* 兼容滚动发布期间的旧后端 */ })
})
</script>

<style scoped>
.tab-toolbar {
  display: flex;
  justify-content: flex-end;
  margin-bottom: 10px;
}
.sort-hint { margin-bottom: 10px; color: var(--el-text-color-secondary); }
.sort-list { display: grid; gap: 8px; }
.sort-item {
  display: flex; align-items: center; gap: 10px; padding: 10px 12px;
  border: 1px solid var(--el-border-color); border-radius: 6px;
  background: var(--el-bg-color-overlay); cursor: grab;
}
.sort-item:active { cursor: grabbing; }
.drag-handle { color: var(--el-text-color-secondary); }
.sort-actions { margin-left: auto; white-space: nowrap; }
</style>
