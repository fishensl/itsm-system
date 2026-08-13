<template>
  <div class="page-container">
    <div class="page-header">
      <h2 class="page-title">账号与部门管理</h2>
      <div class="header-actions">
        <el-button type="primary" :icon="Plus" @click="openCreate">新增用户</el-button>
      </div>
    </div>

    <!-- 用户列表 -->
    <el-card id="section-users" shadow="never" class="section-card">
      <template #header>
        <div class="user-card-header">
          <div>
            <span class="card-title">用户</span>
            <span v-if="currentAccount" class="current-security-status">
              当前账号登录 MFA：
              <el-tag size="small" :type="currentAccount.mfa_enabled ? 'success' : 'warning'">
                {{ currentAccount.mfa_enabled ? '已绑定' : '未绑定' }}
              </el-tag>
            </span>
          </div>
          <el-button
            v-if="currentAccount"
            type="primary"
            size="small"
            @click="openMyMfa"
          >
            {{ currentAccount.mfa_enabled ? '管理 / 更换 MFA' : '绑定我的登录 MFA' }}
          </el-button>
        </div>
      </template>
      <DataTable
        ref="tableRef"
        :columns="userColumns"
        :fetch-data="loadUsers"
        row-key="id"
        :column-settings="{ storageKey: 'cols_users' }"
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
              <el-select v-model="form.roles" multiple collapse-tags collapse-tags-tooltip
                class="w-full" placeholder="可多选（首个为主角色）">
                <el-option v-for="r in roles" :key="r" :label="roleLabelMap[r] || r" :value="r" />
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
          <el-col :xs="24">
            <el-form-item label="企业微信账号">
              <el-input v-model="form.wecom_account" placeholder="企业微信通讯录账号（userid），用于接收系统通知" />
            </el-form-item>
          </el-col>
          <el-col :xs="24" :sm="12">
            <el-form-item label="VPN账号">
              <el-input v-model="form.vpn_account" autocomplete="off" />
            </el-form-item>
          </el-col>
          <el-col :xs="24">
            <el-form-item label="负责区域">
              <el-tree-select
                v-model="form.region_ids"
                :data="regionTree"
                :props="{ label: 'label', children: 'children' }"
                multiple
                show-checkbox
                check-strictly
                node-key="id"
                check-on-click-node
                class="w-full"
                placeholder="多选负责区域（地市/区县），驻场工程师新建工单默认过滤对应区域客户"
              />
            </el-form-item>
          </el-col>
          <el-col :xs="24">
            <el-form-item label="关联客户">
              <el-select
                v-model="form.customer_ids"
                multiple
                filterable
                clearable
                collapse-tags
                class="w-full"
                placeholder="多选该工程师直接负责的客户（搜索选择），不选则按负责区域过滤"
              >
                <el-option v-for="c in customerOptions" :key="c.id" :label="c.name" :value="c.id" />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col v-if="!form.id" :xs="24" :sm="12">
            <el-form-item label="初始密码">
              <el-input v-model="form.password" type="password" show-password autocomplete="new-password"
                placeholder="至少 12 位；用户首次登录后必须修改" />
            </el-form-item>
          </el-col>
          <el-col v-if="form.id" :xs="24" :sm="12">
            <el-form-item label="新密码">
              <el-input v-model="form.password" type="password" show-password autocomplete="new-password"
                placeholder="留空则不修改；设置后用户须再次改密" />
            </el-form-item>
          </el-col>
          <el-col :xs="24">
            <el-form-item label="启用">
              <el-switch v-model="form.is_active" />
            </el-form-item>
          </el-col>
          <el-col :xs="24">
            <el-form-item label="资质证书">
              <div class="cert-groups">
                <div v-for="grp in CERT_GROUPS" :key="grp.group" class="cert-group">
                  <span class="cert-group-name">{{ grp.group }}</span>
                  <el-checkbox-group v-model="form.certifications" size="small">
                    <el-checkbox v-for="c in grp.items" :key="c" :value="c" size="small">{{ c }}</el-checkbox>
                  </el-checkbox-group>
                </div>
              </div>
            </el-form-item>
          </el-col>
        </el-row>
      </el-form>
      <template #footer>
        <el-button @click="formVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="save">保存</el-button>
      </template>
    </el-dialog>

    <!-- 重置密码弹窗 -->
    <el-dialog v-model="resetPwdVisible" title="重置密码" width="400px" destroy-on-close>
      <el-form label-width="90px">
        <el-form-item label="用户">{{ resetTarget?.username }}</el-form-item>
        <el-form-item label="新密码">
          <el-input v-model="resetPwd" type="password" show-password autocomplete="new-password" placeholder="至少 12 位" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="resetPwdVisible = false">取消</el-button>
        <el-button type="primary" :loading="resettingPwd" @click="doResetPwd">确认重置</el-button>
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
import { ElMessageBox } from 'element-plus/es/components/message-box/index'
import { ref, computed, onMounted, watch, h } from 'vue'
import { ElTag } from 'element-plus'
import { nextTick } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Plus } from '@element-plus/icons-vue'
import DataTable, { type DataColumn } from '@/components/DataTable.vue'
import { fetchEntityMeta, mergeFieldMeta, type EntityFieldMeta } from '@/api/meta'
import type { PageResult } from '@/types'
import { useUiStore } from '@/stores/ui'
import { useUserStore } from '@/stores/user'
import { ROLE_LABELS, ROLE_TAG, ACTIVE_LABELS } from '@/utils/labels'
import {
  fetchUsers, createUser, updateUser, deleteUser, resetUserPassword, resetUserMfa, offboardUser,
  fetchDepartments, createDepartment, updateDepartment, deleteDepartment,
  type UserItem, type DepartmentItem,
} from '@/api/system'
import { fetchRegions, type RegionItem } from '@/api/regions'
import { fetchCustomers } from '@/api/customers'

const ui = useUiStore()
const userStore = useUserStore()
const router = useRouter()
interface DeptRow {
  id: number
  name: string
  parent_id: number | null
  head_id: number | null
  sort_order: number
}

const users = ref<UserItem[]>([])
const currentAccount = computed(() => users.value.find((item) => item.id === userStore.user?.id))

function openMyMfa() {
  router.push('/mfa')
}
const depts = ref<DeptRow[]>([])
const allUsers = ref<{ id: number; name: string }[]>([])
const roles = ref<string[]>([])
const roleNames = ref<Record<string, string>>({})
const tableRef = ref()
const userFieldMeta = ref<EntityFieldMeta[]>([])

/** 角色名称映射（内置 + 自定义角色），列表列/下拉统一用名称展示 */
const roleLabelMap = computed(() => ({ ...ROLE_LABELS, ...roleNames.value }))

// 关联客户选项（全量，供搜索勾选）
const customerOptions = ref<{ id: number; name: string }[]>([])

async function loadCustomers() {
  try {
    const d = await fetchCustomers({ page: 1, page_size: 1000 })
    customerOptions.value = d.items.map((c) => ({ id: c.id, name: c.name }))
  } catch { /* toast */ }
}

// 负责区域树（地市 → 区县，多选）
const regionTree = ref<{ id: number; label: string; children: { id: number; label: string }[] }[]>([])

async function loadRegions() {
  try {
    const regions = await fetchRegions()
    regionTree.value = regions.map((r: RegionItem) => ({
      id: r.id,
      label: r.name,
      children: (r.children || []).map((c) => ({ id: c.id, label: c.name })),
    }))
  } catch { /* toast */ }
}

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
  roles.value = data.roles
  roleNames.value = data.role_names || {}
  // 部门列表须用 /api/departments 的 departments（含 head_id/parent_id/sort_order），
  // /api/users 返回的 departments 只有 id/name（负责人列/回填曾因此失效）
  const deptData = await fetchDepartments()
  depts.value = (deptData.departments as unknown as DeptRow[])
  allUsers.value = deptData.users
}

const loadUsers = async (params: Record<string, unknown>): Promise<PageResult<Record<string, any>>> => {
  const data = await fetchUsers(params)
  return {
    items: data.users as unknown as Record<string, any>[],
    total: data.total ?? data.users.length,
    page: data.page ?? 1,
    page_size: data.page_size ?? (data.users.length || 20),
  }
}

const userColumns = computed(() => mergeFieldMeta([
  { key: 'username', label: '用户名', minWidth: 110, asTitle: true },
  { key: 'realname', label: '姓名', width: 90 },
  { key: 'roles', label: '角色', width: 180, type: 'custom',
    render: (row: Record<string, unknown>) => {
      const rowRoles = row.roles as string[] | undefined
      const codes: string[] = rowRoles?.length ? rowRoles : [(row.role as string) || 'viewer']
      return h('div', codes.map((c) => h(ElTag, {
        size: 'small', type: ROLE_TAG[c] || 'info', style: 'margin-right:4px',
      }, () => roleLabelMap.value[c] || c)))
    } },
  { key: 'department_name', label: '部门', minWidth: 100 },
  { key: 'region_names', label: '负责区域', minWidth: 130 },
  { key: 'customer_names', label: '关联客户', minWidth: 130 },
  { key: 'is_active', label: '状态', width: 80, type: 'tag', asTag: true,
    tagMap: { true: 'success', false: 'info' }, valueMap: ACTIVE_LABELS },
  { key: 'phone', label: '电话', minWidth: 110 },
  { key: 'vpn_account', label: 'VPN账号', minWidth: 110, defaultVisible: false },
  { key: 'mfa_enabled', label: '登录MFA', width: 90, type: 'tag',
    tagMap: { true: 'success', false: 'info' }, valueMap: { true: '已绑定', false: '未绑定' } },
  { key: 'mfa_op_enabled', label: '操作码', width: 90, type: 'tag',
    tagMap: { true: 'success', false: 'info' }, valueMap: { true: '已绑定', false: '未绑定' } },
  { key: 'created_at', label: '创建时间', width: 100 },
  { key: 'actions', label: '操作', width: 280, type: 'action', fixed: 'right',
    actions: [
      { label: '绑定MFA', type: 'success', link: true,
        visible: (row) => row.id === userStore.user?.id && !row.mfa_enabled,
        onClick: () => openMyMfa() },
      { label: '更换MFA', type: 'warning', link: true,
        visible: (row) => row.id === userStore.user?.id && Boolean(row.mfa_enabled),
        onClick: () => openMyMfa() },
      { label: '编辑', type: 'primary', link: true, icon: 'Edit', perm: 'user:edit',
        onClick: (row) => openEdit(row as unknown as UserItem) },
      { label: '重置密码', type: 'warning', link: true, perm: 'user:edit',
        onClick: (row) => openResetPwd(row as unknown as UserItem) },
      { label: '重置MFA', type: 'warning', link: true, perm: 'mfa:manage',
        onClick: (row) => onResetMfa(row as unknown as UserItem) },
      { label: '离职清理', type: 'danger', link: true, perm: 'mfa:manage',
        disabled: (row) => !row.is_active,
        onClick: (row) => onOffboard(row as unknown as UserItem) },
      { label: '删除', type: 'danger', link: true, icon: 'Delete', perm: 'user:delete',
        onClick: (row) => onDelete(row as unknown as UserItem) },
    ] },
] as DataColumn[], userFieldMeta.value))

// 用户表单
const formVisible = ref(false)
const saving = ref(false)
const formRef = ref()
const form = ref<Record<string, unknown>>({})
const formRules = { username: [{ required: true, message: '请输入用户名', trigger: 'blur' }] }

// 证书选项（对齐后端 utils/cert_options.py）
const CERT_GROUPS = [
  { group: '华为', items: ['HCIA', 'HCIP', 'HCIE'] },
  { group: 'H3C', items: ['H3CNE', 'H3CSE', 'H3CIE'] },
  { group: '软考', items: ['网络管理员', '网络工程师', '网络规划设计师'] },
  { group: '国家注册信息安全', items: ['CISP', 'CISP-PTE', 'CISP-PTS'] },
]

// 重置密码
const resetPwdVisible = ref(false)
const resetTarget = ref<UserItem | null>(null)
const resetPwd = ref('')
const resettingPwd = ref(false)

function openResetPwd(u: UserItem) {
  resetTarget.value = u
  resetPwd.value = ''
  resetPwdVisible.value = true
}

async function doResetPwd() {
  if (!resetTarget.value) return
  if (resetPwd.value.length < 12) {
    ui.toast('新密码长度至少 12 位', 'warning')
    return
  }
  resettingPwd.value = true
  try {
    await resetUserPassword(resetTarget.value.id, resetPwd.value)
    ui.toast('密码已重置', 'success')
    resetPwdVisible.value = false
  } catch (e) {
    ui.toast((e as Error).message, 'error')
  } finally {
    resettingPwd.value = false
  }
}

function openCreate() {
  form.value = { username: '', realname: '', roles: ['viewer'], department_id: null,
    phone: '', email: '', wecom_account: '', vpn_account: '', password: '', is_active: true, certifications: [],
    region_ids: [], customer_ids: [] }
  formVisible.value = true
}

function openEdit(u: UserItem) {
  form.value = { id: u.id, username: u.username, realname: u.realname,
    roles: (u.roles && u.roles.length ? [...u.roles] : [u.role || 'viewer']),
    department_id: u.department_id, phone: u.phone, email: u.email,
    wecom_account: u.notify_accounts?.wecom || '',
    vpn_account: u.vpn_account || '',
    password: '', is_active: u.is_active, certifications: [...(u.certifications || [])],
    region_ids: [...(u.region_ids || [])], customer_ids: [...(u.customer_ids || [])] }
  formVisible.value = true
}

async function save() {
  try { await formRef.value?.validate() } catch { return }
  saving.value = true
  try {
    const payload = { ...form.value }
    // 通知账号合并写入（仅企微字段本期开放，其余渠道启用后自动扩展）
    payload.notify_accounts = { wecom: payload.wecom_account || '' }
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

async function onResetMfa(u: UserItem) {
  try {
    await ElMessageBox.confirm(`重置「${u.username}」的登录 MFA、操作码和恢复码？`,
      '重置 MFA', { type: 'warning' })
  } catch { return }
  try {
    await resetUserMfa(u.id)
    ui.toast('MFA 已重置，用户现有会话将失效', 'success')
    tableRef.value?.refresh()
  } catch (e) { ui.toast((e as Error).message, 'error') }
}

async function onOffboard(u: UserItem) {
  try {
    await ElMessageBox.confirm(
      `离职清理只撤销「${u.username}」的访问权限和认证凭据；工单、巡检、报告、审计等历史记录全部保留。是否继续？`,
      '离职清理', { type: 'warning', confirmButtonText: '撤销访问权限' })
  } catch { return }
  try {
    const result = await offboardUser(u.id)
    const hasWarnings = Boolean(result.hook_warnings?.length)
    ui.toast(hasWarnings ? '访问已撤销，外部钩子执行失败，请查日志' : '访问权限已撤销',
      hasWarnings ? 'warning' : 'success')
    tableRef.value?.refresh()
  } catch (e) { ui.toast((e as Error).message, 'error') }
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
  loadRegions()
  loadCustomers()
  fetchEntityMeta('user').then((meta) => {
    userFieldMeta.value = meta?.profiles.list || []
  })
})
</script>

<style scoped>
.section-card { margin-bottom: 12px; }
.card-title { font-weight: 600; font-size: 14px; }
.user-card-header { display: flex; justify-content: space-between; align-items: center; gap: 12px; }
.current-security-status { margin-left: 18px; color: var(--itsm-text-muted); font-size: 12px; }
.dept-header { display: flex; justify-content: space-between; align-items: center; }
.w-full { width: 100%; }
@media (max-width: 640px) {
  .user-card-header { align-items: flex-start; flex-direction: column; }
  .current-security-status { display: block; margin: 6px 0 0; }
}
</style>
