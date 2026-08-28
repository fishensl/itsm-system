<template>
  <div class="page-container">
    <div class="page-header">
      <h2 class="page-title">单位类别</h2>
      <div class="header-actions">
        <el-button v-if="user.hasPerm('category:edit')" @click="openSort">拖动排序</el-button>
        <el-button v-if="user.hasPerm('category:edit')" type="primary" :icon="Plus" @click="openCreate">
          新增类别
        </el-button>
      </div>
    </div>

    <el-card shadow="never">
      <DataTable
        ref="tableRef"
        :columns="columns"
        :fetch-data="fetchPage"
        row-key="id"
        :column-settings="{ storageKey: 'cols_customer_categories' }"
      />
    </el-card>

    <el-dialog v-model="formVisible" :title="form.id ? '编辑类别' : '新增类别'" width="420px" destroy-on-close>
      <el-form ref="formRef" :model="form" label-width="90px">
        <el-form-item label="名称" prop="name" :rules="[{ required: true, message: '请输入名称', trigger: 'blur' }]">
          <el-input v-model="form.name" placeholder="如：水利局" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="formVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="save">保存</el-button>
      </template>
    </el-dialog>
    <el-dialog v-model="sortVisible" title="拖动排序" width="460px">
      <div class="sort-list">
        <div v-for="(item, index) in sortItems" :key="item.id" class="sort-item"
          draggable="true" @dragstart="dragIndex = index" @dragover.prevent @drop="dropSort(index)">
          <span class="drag-handle">☰</span><span>{{ item.name }}</span>
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
  </div>
</template>

<script setup lang="ts">
import { ElMessageBox } from 'element-plus/es/components/message-box/index'
import { ref, reactive, onMounted, computed } from 'vue'
import { Plus } from '@element-plus/icons-vue'
import DataTable, { type DataColumn } from '@/components/DataTable.vue'
import { fetchEntityMeta, mergeFieldMeta, type EntityFieldMeta } from '@/api/meta'
import { fetchCategories, createCategory, updateCategory, deleteCategory, reorderCategories, type CategoryItem } from '@/api/regions'
import { useUserStore } from '@/stores/user'
import { useUiStore } from '@/stores/ui'

const user = useUserStore()
const ui = useUiStore()
const tableRef = ref()
const fieldMeta = ref<EntityFieldMeta[]>([])
const formVisible = ref(false)
const saving = ref(false)
const formRef = ref()
const form = reactive<Record<string, unknown>>({ id: null, name: '' })
const sortVisible = ref(false)
const sortSaving = ref(false)
const sortItems = ref<CategoryItem[]>([])
const dragIndex = ref<number | null>(null)

// S7-1 DataTable：列配置 + 分页包装（fetchCategories 返回裸数组）
const columns = computed<DataColumn[]>(() => mergeFieldMeta([
  { key: 'name', label: '类别名称', minWidth: 200, asTitle: true },
  { key: 'sort_order', label: '排序', width: 100 },
  { key: 'actions', label: '操作', width: 150, type: 'action', fixed: 'right',
    actions: [
      { label: '编辑', type: 'primary', link: true, perm: 'category:edit',
        onClick: (row) => openEdit(row as unknown as CategoryItem) },
      { label: '删除', type: 'danger', link: true, perm: 'category:edit',
        onClick: (row) => onDelete(row as unknown as CategoryItem) },
    ] },
], fieldMeta.value))

async function fetchPage(params: Record<string, unknown>) {
  const list = await fetchCategories()
  const page = Number(params.page) || 1
  const page_size = Number(params.page_size) || 20
  const start = (page - 1) * page_size
  return { items: list.slice(start, start + page_size), total: list.length,
    page, page_size }
}

function load() {
  tableRef.value?.refresh()
}

function openCreate() {
  Object.assign(form, { id: null, name: '' })
  formVisible.value = true
}

function openEdit(row: CategoryItem) {
  Object.assign(form, { id: row.id, name: row.name })
  formVisible.value = true
}

async function save() {
  try { await formRef.value?.validate() } catch { return }
  saving.value = true
  try {
    const payload = { name: String(form.name) }
    if (form.id) {
      await updateCategory(form.id as number, payload)
      ui.toast('已保存', 'success')
    } else {
      await createCategory(payload)
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
  sortItems.value = [...await fetchCategories()]
  sortVisible.value = true
}

function dropSort(target: number) {
  if (dragIndex.value == null || dragIndex.value === target) return
  const next = [...sortItems.value]
  const [moved] = next.splice(dragIndex.value, 1)
  next.splice(target, 0, moved)
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
    await reorderCategories(sortItems.value.map((item) => item.id))
    ui.toast('排序已保存', 'success')
    sortVisible.value = false
    load()
  } catch (e) {
    ui.toast((e as Error).message, 'error')
  } finally {
    sortSaving.value = false
  }
}

async function onDelete(row: CategoryItem) {
  try {
    await ElMessageBox.confirm(`确定删除类别「${row.name}」吗？`, '删除确认', { type: 'warning' })
  } catch { return }
  try {
    await deleteCategory(row.id)
    ui.toast('已删除', 'success')
    load()
  } catch (e) {
    ui.toast((e as Error).message, 'error')
  }
}

onMounted(() => {
  load()
  fetchEntityMeta('customer_category').then((meta) => {
    fieldMeta.value = meta?.profiles.list || []
  })
})
</script>

<style scoped>
.sort-list { display: grid; gap: 8px; }
.sort-item { display: flex; gap: 10px; padding: 10px 12px; border: 1px solid var(--itsm-border); border-radius: 6px; cursor: grab; }
.drag-handle { color: var(--itsm-text-muted); }
.sort-actions { margin-left: auto; white-space: nowrap; }
</style>
