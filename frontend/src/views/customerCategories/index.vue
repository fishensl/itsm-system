<template>
  <div class="page-container">
    <div class="page-header">
      <h2 class="page-title">单位类别</h2>
      <div class="header-actions">
        <el-button v-if="user.hasPerm('category:edit')" type="primary" :icon="Plus" @click="openCreate">
          新增类别
        </el-button>
      </div>
    </div>

    <el-card shadow="never">
      <el-table v-loading="loading" :data="items" border size="default" row-key="id">
        <el-table-column prop="name" label="类别名称" min-width="200" />
        <el-table-column prop="sort_order" label="排序" width="100" />
        <el-table-column v-if="user.hasPerm('category:edit')" label="操作" width="150" fixed="right">
          <template #default="{ row }">
            <el-button size="small" link type="primary" @click="openEdit(row)">编辑</el-button>
            <el-button size="small" link type="danger" @click="onDelete(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
      <el-empty v-if="!loading && !items.length" description="暂无类别" :image-size="60" />
    </el-card>

    <el-dialog v-model="formVisible" :title="form.id ? '编辑类别' : '新增类别'" width="420px" destroy-on-close>
      <el-form ref="formRef" :model="form" label-width="90px">
        <el-form-item label="名称" prop="name" :rules="[{ required: true, message: '请输入名称', trigger: 'blur' }]">
          <el-input v-model="form.name" placeholder="如：水利局" />
        </el-form-item>
        <el-form-item label="排序">
          <el-input-number v-model="form.sort_order" :min="0" />
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
import { ref, reactive, onMounted } from 'vue'
import { Plus } from '@element-plus/icons-vue'
import { fetchCategories, createCategory, updateCategory, deleteCategory, type CategoryItem } from '@/api/regions'
import { useUserStore } from '@/stores/user'
import { useUiStore } from '@/stores/ui'

const user = useUserStore()
const ui = useUiStore()
const items = ref<CategoryItem[]>([])
const loading = ref(false)
const formVisible = ref(false)
const saving = ref(false)
const formRef = ref()
const form = reactive<Record<string, unknown>>({ id: null, name: '', sort_order: 0 })

function load() {
  loading.value = true
  fetchCategories()
    .then((d) => { items.value = d })
    .catch(() => { /* toast */ })
    .finally(() => { loading.value = false })
}

function openCreate() {
  Object.assign(form, { id: null, name: '', sort_order: 0 })
  formVisible.value = true
}

function openEdit(row: CategoryItem) {
  Object.assign(form, { id: row.id, name: row.name, sort_order: row.sort_order })
  formVisible.value = true
}

async function save() {
  try { await formRef.value?.validate() } catch { return }
  saving.value = true
  try {
    const payload = { name: String(form.name), sort_order: Number(form.sort_order || 0) }
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

onMounted(load)
</script>
