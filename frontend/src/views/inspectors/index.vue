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
      <el-table
        v-loading="loading"
        :data="data?.inspectors || []"
        border
        size="default"
        row-key="id"
      >
        <el-table-column prop="name" label="姓名" min-width="120" />
        <el-table-column prop="username" label="用户名" min-width="120" />
        <el-table-column prop="phone" label="手机" min-width="130">
          <template #default="{ row }">{{ row.phone || '-' }}</template>
        </el-table-column>
        <el-table-column prop="email" label="邮箱" min-width="180">
          <template #default="{ row }">{{ row.email || '-' }}</template>
        </el-table-column>
        <el-table-column prop="is_active" label="状态" width="90">
          <template #default="{ row }">
            <el-tag size="small" :type="row.is_active ? 'success' : 'info'">
              {{ row.is_active ? '启用' : '停用' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="remark" label="备注" min-width="140">
          <template #default="{ row }">{{ row.remark || '-' }}</template>
        </el-table-column>
        <el-table-column v-if="user.hasPerm('inspection:edit')" label="操作" width="160" fixed="right">
          <template #default="{ row }">
            <el-button size="small" link type="primary" @click="openEdit(row)">编辑</el-button>
            <el-button v-if="user.hasPerm('inspection:delete')" size="small" link type="danger"
              @click="onDelete(row)">移除</el-button>
          </template>
        </el-table-column>
      </el-table>
      <el-empty v-if="!loading && !data?.inspectors?.length" description="暂无巡检人员" :image-size="60" />
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
import { ref, reactive, onMounted } from 'vue'
import { Plus } from '@element-plus/icons-vue'
import {
  fetchInspectors, createInspector, updateInspector, deleteInspector,
  type InspectorListData, type InspectorItem,
} from '@/api/inspectors'
import { useUserStore } from '@/stores/user'
import { useUiStore } from '@/stores/ui'

const user = useUserStore()
const ui = useUiStore()
const data = ref<InspectorListData | null>(null)
const loading = ref(false)

const formVisible = ref(false)
const saving = ref(false)
const formRef = ref()
const form = reactive<Record<string, unknown>>({
  id: null, user_id: undefined, user_name: '', is_active: true, remark: '',
})

function load() {
  loading.value = true
  fetchInspectors()
    .then((d) => { data.value = d })
    .catch(() => { /* toast */ })
    .finally(() => { loading.value = false })
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

onMounted(load)
</script>

<style scoped>
.form-tip {
  font-size: 12px;
  color: var(--itsm-text-muted);
  line-height: 1.5;
}
</style>
