<template>
  <div class="page-container">
    <div class="page-header">
      <h2 class="page-title">用户与部门管理</h2>
      <div class="header-actions">
        <el-button type="primary" :icon="Plus" @click="openCreate">新增用户</el-button>
      </div>
    </div>

    <!-- 用户列表 -->
    <el-card id="section-users" shadow="never" class="section-card">
      <template #header><span class="card-title">用户</span></template>
      <DataTable
        ref="tableRef"
        :columns="userColumns"
        :fetch-data="loadUsers"
        row-key="id"
      />
    </el-card>

    <!-- 部门列表 -->
    <el-card id="section-depts" shadow="never" class="section-card">
      <template #header>
        <div class="dept-header">
          <span class="card-title">部门</span>
          <el-button size="small" :icon="Plus" @click="openDeptCreate">新增部门</el-button>
        </div>
      </template>
      <el-table v-if="depts.length" :data="deptTree" size="small" border>
        <el-table-column prop="name" label="部门名称" min-width="180" />
        <el-table-column label="负责人" min-width="100">
          <template #default="{ row }">
            {{ userName(row.head_id) }}
          </template>
        </el-table-column>
        <el-table-column label="排序" prop="sort_order" width="70" />
        <el-table-column label="操作" width="120">
          <template #default="{ row }">
            <el-button size="small" link type="primary" @click="openDeptEdit(row)">编辑</el-button>
            <el-button size="small" link type="danger" @click="onDeptDelete(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
      <el-empty v-else description="暂无部门" :image-size="50" />
    </el-card>

    <!-- 用户表单 -->
    <el-dialog v-model="formVisible" :title="form.id ? '编辑用户' : '新增用户'" width="560px"
      destroy-on-close>
      <el-form ref="formRef" :model="form" :rules="formRules" label-width="90px">
        <el-row :gutter="12">
          <el-col :xs="24" :sm="12">
            <el-form-item label="用户名" prop="username">
              <el-input v-model="form.username" />
            </el-form-item>
          </el-col>
          <el-col :xs="24" :sm="12">
            <el-form-item label="姓名">
              <el-input v-model="form.realname" />
            </el-form-item>
          </el-col>
          <el-col :xs="24" :sm="12">
            <el-form-item label="角色">
              <el-select v-model="form.role" class="w-full">
                <el-option v-for="r in roles" :key="r" :label="r" :value="r" />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :xs="24" :sm="12">
            <el-form-item label="部门">
              <el-select v-model="form.department_id" clearable class="w-full">
                <el-option v-for="d in depts" :key="d.id" :label="d.name" :value="d.id" />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :xs="24" :sm="12">
            <el-form-item label="电话">
              <el-input v-model="form.phone" />
            </el-form-item>
          </el-col>
          <el-col :xs="24" :sm="12">
            <el-form-item label="邮箱">
              <el-input v-model="form.email" />
            </el-form-item>
          </el-col>
          <el-col v-if="!form.id" :xs="24" :sm="12">
            <el-form-item label="初始密码">
              <el-input v-model="form.password" type="password" show-password />
            </el-form-item>
          </el-col>
          <el-col v-if="form.id" :xs="24" :sm="12">
            <el-form-item label="新密码">
              <el-input v-model="form.password" type="password" show-password
                placeholder="留空则不修改" />
            </el-form-item>
          </el-col>
          <el-col :xs="24">
            <el-form-item label="启用">
              <el-switch v-model="form.is_active" />
            </el-form-item>
          </el-col>
        </el-row>
      </el-form>
      <template #footer>
        <el-button @click="formVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="save">保存</el-button>
      </template>
    </el-dialog>

    <!-- 部门表单 -->
    <el-dialog v-model="deptFormVisible" :title="deptForm.id ? '编辑部门' : '新增部门'" width="460px"
      destroy-on-close>
      <el-form label-width="90px">
        <el-form-item label="部门名称">
          <el-input v-model="deptForm.name" />
        </el-form-item>
        <el-form-item label="上级部门">
          <el-select v-model="deptForm.parent_id" clearable class="w-full">
            <el-option v-for="d in depts" :key="d.id" :label="d.name" :value="d.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="负责人">
          <el-select v-model="deptForm.head_id" clearable filterable class="w-full">
            <el-option v-for="u in allUsers" :key="u.id" :label="u.name" :value="u.id" />
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="deptFormVisible = false">取消</el-button>
        <el-button type="primary" @click="saveDept">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import { nextTick } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessageBox } from 'element-plus'
import { Plus } from '@element-plus/icons-vue'
import DataTable, { type DataColumn } from '@/components/DataTable.vue'
import { useUiStore } from '@/stores/ui'
import {
  fetchUsers, createUser, updateUser, deleteUser,
  fetchDepartments, createDepartment, updateDepartment, deleteDepartment,
  type UserItem, type DepartmentItem,
} from '@/api/system'

const ui = useUiStore()
interface DeptRow {
  id: number
  name: string
  parent_id: number | null
  head_id: number | null
  sort_order: number
}

const users = ref<UserItem[]>([])
const depts = ref<DeptRow[]>([])
const allUsers = ref<{ id: number; name: string }[]>([])
const roles = ref<string[]>([])
const tableRef = ref()

// 侧栏入口（/app/system/users?tab=departments 等）滚动定位对应区块
const route = useRoute()
watch(
  () => route.query.tab,
  (tab) => {
    if (tab && ['users', 'departments'].includes(String(tab))) {
      nextTick(() => {
        document.getElementById(`section-${tab}`)?.scrollIntoView({ behavior: 'smooth', block: 'start' })
      })
    }
  },
  { immediate: true },
)

const deptTree = computed(() => depts.value.filter((d) => !d.parent_id))

function userName(id: number | null) {
  return allUsers.value.find((u) => u.id === id)?.name || '-'
}

async function load() {
  const data = await fetchUsers()
  users.value = data.users
  depts.value = (data.departments as unknown as DeptRow[])
  roles.value = data.roles
  const deptData = await fetchDepartments()
  allUsers.value = deptData.users
}

const loadUsers = async (): Promise<{ items: Record<string, any>[]; total: number; page: number; page_size: number }> => ({
  items: users.value as unknown as Record<string, any>[],
  total: users.value.length,
  page: 1,
  page_size: users.value.length || 20,
})

const userColumns = computed(() => [
  { key: 'username', label: '用户名', minWidth: 110, asTitle: true },
  { key: 'realname', label: '姓名', width: 90 },
  { key: 'role', label: '角色', width: 90, type: 'tag',
    tagMap: { admin: 'danger', operator: 'primary', sales: 'warning', viewer: 'info' } },
  { key: 'department_name', label: '部门', minWidth: 100 },
  { key: 'is_active', label: '状态', width: 80, type: 'tag', asTag: true,
    tagMap: { true: 'success', false: 'info' } },
  { key: 'phone', label: '电话', minWidth: 110 },
  { key: 'created_at', label: '创建时间', width: 100 },
  { key: 'actions', label: '操作', width: 110, type: 'action', fixed: 'right',
    actions: [
      { label: '编辑', type: 'primary', link: true, icon: 'Edit', onClick: (row) => openEdit(row as unknown as UserItem) },
      { label: '删除', type: 'danger', link: true, icon: 'Delete', onClick: (row) => onDelete(row as unknown as UserItem) },
    ] },
] as DataColumn[])

// 用户表单
const formVisible = ref(false)
const saving = ref(false)
const formRef = ref()
const form = ref<Record<string, unknown>>({})
const formRules = { username: [{ required: true, message: '请输入用户名', trigger: 'blur' }] }

function openCreate() {
  form.value = { username: '', realname: '', role: 'viewer', department_id: null,
    phone: '', email: '', password: '', is_active: true }
  formVisible.value = true
}

function openEdit(u: UserItem) {
  form.value = { id: u.id, username: u.username, realname: u.realname, role: u.role,
    department_id: u.department_id, phone: u.phone, email: u.email,
    password: '', is_active: u.is_active }
  formVisible.value = true
}

async function save() {
  try { await formRef.value?.validate() } catch { return }
  saving.value = true
  try {
    const payload = { ...form.value }
    if (payload.id) {
      await updateUser(payload.id as number, payload)
      ui.toast('用户已更新', 'success')
    } else {
      await createUser(payload)
      ui.toast('用户已创建', 'success')
    }
    formVisible.value = false
    await load()
    tableRef.value?.refresh()
  } catch (e) {
    ui.toast((e as Error).message, 'error')
  } finally {
    saving.value = false
  }
}

async function onDelete(u: UserItem) {
  try {
    await ElMessageBox.confirm(`确定删除用户「${u.username}」吗？`, '删除确认', { type: 'warning' })
  } catch { return }
  try {
    await deleteUser(u.id)
    ui.toast('已删除', 'success')
    await load()
    tableRef.value?.refresh()
  } catch (e) {
    ui.toast((e as Error).message, 'error')
  }
}

// 部门表单
const deptFormVisible = ref(false)
const deptForm = ref<Record<string, unknown>>({})

function openDeptCreate() {
  deptForm.value = { name: '', parent_id: null, head_id: null }
  deptFormVisible.value = true
}

function openDeptEdit(d: DepartmentItem) {
  deptForm.value = { id: d.id, name: d.name, parent_id: d.parent_id, head_id: d.head_id }
  deptFormVisible.value = true
}

async function saveDept() {
  const payload = { ...deptForm.value }
  try {
    if (payload.id) await updateDepartment(payload.id as number, payload)
    else await createDepartment(payload)
    ui.toast('已保存', 'success')
    deptFormVisible.value = false
    await load()
  } catch (e) {
    ui.toast((e as Error).message, 'error')
  }
}

async function onDeptDelete(d: DepartmentItem) {
  try {
    await ElMessageBox.confirm(`确定删除部门「${d.name}」吗？`, '删除确认', { type: 'warning' })
  } catch { return }
  try {
    await deleteDepartment(d.id)
    ui.toast('已删除', 'success')
    await load()
  } catch (e) {
    ui.toast((e as Error).message, 'error')
  }
}

onMounted(() => {
  load()
})
</script>

<style scoped>
.section-card { margin-bottom: 12px; }
.card-title { font-weight: 600; font-size: 14px; }
.dept-header { display: flex; justify-content: space-between; align-items: center; }
.w-full { width: 100%; }
</style>
