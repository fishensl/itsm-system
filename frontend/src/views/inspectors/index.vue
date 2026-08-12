<template>
  <div class="page-container">
    <div class="page-header">
      <h2 class="page-title">巡检人员</h2>
      <div class="header-actions">
        <el-button
          v-if="user.hasPerm('inspection:edit')"
          type="primary"
          :icon="Plus"
          @click="openCreate"
        >
          添加巡检人员
        </el-button>
      </div>
    </div>

    <el-card shadow="never">
      <DataTable
        ref="tableRef"
        :columns="columns"
        :fetch-data="fetchPage"
        row-key="id"
        :column-settings="{ storageKey: 'cols_inspectors' }"
      />
    </el-card>

    <!-- 添加 / 编辑弹窗 -->
    <el-dialog
      v-model="formVisible"
      :title="form.id ? '编辑巡检人员' : '添加巡检人员'"
      width="480px"
      destroy-on-close
    >
      <el-form ref="formRef" :model="form" label-width="90px">
        <el-form-item
          v-if="!form.id"
          label="选择用户"
          prop="user_id"
          :rules="[{ required: true, message: '请选择用户', trigger: 'change' }]"
        >
          <el-select v-model="form.user_id" placeholder="选择可勾选的用户" filterable style="width: 100%">
            <el-option
              v-for="u in data?.available_users || []"
              :key="u.id"
              :label="`${u.name}（${u.username}）`"
              :value="u.id"
            />
          </el-select>
          <div v-if="!data?.available_users?.length" class="form-tip">
            暂无可用用户（需启用状态且角色为操作员/管理员且未关联）
          </div>
        </el-form-item>
        <el-form-item v-if="form.id" label="用户">
          <el-input :model-value="form.user_name" disabled />
        </el-form-item>
        <el-form-item label="状态">
          <el-switch v-model="form.is_active" :active-text="form.is_active ? '启用' : '停用'" />
        </el-form-item>
        <el-form-item label="备注">
          <el-input v-model="form.remark" type="textarea" :rows="3" placeholder="备注（可选）" />
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
import DataTable, { type DataColumn } from '@/components/DataTable.vue'
import { fetchEntityMeta, mergeFieldMeta, type EntityFieldMeta } from '@/api/meta'
import {
  fetchInspectors, createInspector, updateInspector, deleteInspector,
  type InspectorListData, type InspectorItem,
} from '@/api/inspectors'
import { useUserStore } from '@/stores/user'
import { useUiStore } from '@/stores/ui'

const user = useUserStore()
const ui = useUiStore()
const tableRef = ref()
const data = ref<InspectorListData | null>(null)
const loading = ref(false)
const fieldMeta = ref<EntityFieldMeta[]>([])

const formVisible = ref(false)
const saving = ref(false)
const formRef = ref()
const form = reactive<Record<string, unknown>>({
  id: null, user_id: undefined, user_name: '', is_active: true, remark: '',
})

// S7-1 DataTable：列配置 + 分页包装
const columns = computed<DataColumn[]>(() => mergeFieldMeta([
  { key: 'name', label: '姓名', minWidth: 120, asTitle: true },
  { key: 'username', label: '用户名', minWidth: 120 },
  { key: 'phone', label: '手机', minWidth: 130, render: (r) => r.phone || '-' },
  { key: 'email', label: '邮箱', minWidth: 180, render: (r) => r.email || '-' },
  { key: 'is_active', label: '状态', width: 90, type: 'tag', tagMap: { true: 'success', false: 'info' },
    render: (r) => (r.is_active ? '启用' : '停用') },
  { key: 'remark', label: '备注', minWidth: 140, render: (r) => r.remark || '-' },
  { key: 'actions', label: '操作', width: 160, type: 'action', fixed: 'right',
    actions: [
      { label: '编辑', type: 'primary', link: true, perm: 'inspection:edit',
        onClick: (row) => openEdit(row as unknown as InspectorItem) },
      { label: '移除', type: 'danger', link: true, perm: 'inspection:delete',
        onClick: (row) => onDelete(row as unknown as InspectorItem) },
    ] },
], fieldMeta.value))

async function fetchPage(params: Record<string, unknown>) {
  const d = await fetchInspectors()
  data.value = d
  const page = Number(params.page) || 1
  const page_size = Number(params.page_size) || 20
  const list = d.inspectors || []
  const start = (page - 1) * page_size
  return { items: list.slice(start, start + page_size), total: list.length,
    page, page_size }
}

function load() {
  tableRef.value?.refresh()
}

function openCreate() {
  Object.assign(form, { id: null, user_id: undefined, user_name: '', is_active: true, remark: '' })
  formVisible.value = true
}

function openEdit(row: InspectorItem) {
  Object.assign(form, {
    id: row.id, user_id: row.user_id, user_name: row.name, is_active: row.is_active, remark: row.remark,
  })
  formVisible.value = true
}

async function save() {
  try { await formRef.value?.validate() } catch { return }
  saving.value = true
  try {
    if (form.id) {
      await updateInspector(form.id as number, { is_active: !!form.is_active, remark: String(form.remark || '') })
      ui.toast('已更新', 'success')
    } else {
      await createInspector({ user_id: form.user_id as number, remark: String(form.remark || '') })
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

async function onDelete(row: InspectorItem) {
  try {
    await ElMessageBox.confirm(`确定移除巡检人员「${row.name}」吗？`, '移除确认', { type: 'warning' })
  } catch { return }
  try {
    await deleteInspector(row.id)
    ui.toast('已移除', 'success')
    load()
  } catch (e) {
    ui.toast((e as Error).message, 'error')
  }
}

onMounted(() => {
  load()
  fetchEntityMeta('inspector').then((meta) => {
    fieldMeta.value = meta?.profiles.list || []
  })
})
</script>

<style scoped>
.form-tip {
  font-size: 12px;
  color: var(--itsm-text-muted);
  line-height: 1.5;
}
</style>
