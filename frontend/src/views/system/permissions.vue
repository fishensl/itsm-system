<template>
  <div class="page-container">
    <div class="page-header">
      <h2 class="page-title">权限管理</h2>
      <div class="header-actions">
        <el-button v-if="user.hasPerm('permission:edit')" type="primary" :icon="Plus" @click="openRoleCreate">
          新增角色
        </el-button>
      </div>
    </div>

    <el-tabs v-model="activeTab">
      <!-- 角色列表 -->
      <el-tab-pane label="角色列表" name="list">
        <el-card shadow="never">
          <DataTable
            ref="roleTableRef"
            :columns="roleColumns"
            :fetch-data="fetchRolePage"
            row-key="code"
            :column-settings="{ storageKey: 'cols_permissions_roles' }"
          />
        </el-card>
      </el-tab-pane>

      <!-- 角色权限矩阵 -->
      <el-tab-pane label="角色权限" name="matrix">
        <el-card shadow="never">
          <div v-loading="loading" class="matrix-scroll">
            <table class="perm-table">
              <thead>
                <tr>
                  <th class="sticky-col">权限</th>
                  <th v-for="r in activeRoles" :key="r.code" class="role-col">
                    {{ r.name }}
                  </th>
                </tr>
              </thead>
              <tbody>
                <template v-for="(group, gi) in groupedPerms" :key="gi">
                  <tr class="group-row">
                    <td class="sticky-col" :colspan="activeRoles.length + 1">{{ group.name }}</td>
                  </tr>
                  <tr v-for="p in group.items" :key="p.code">
                    <td class="sticky-col">
                      <div class="perm-cell">
                        <span class="perm-label">{{ p.label }}</span>
                        <code class="perm-code">{{ p.code }}</code>
                      </div>
                    </td>
                    <td v-for="r in activeRoles" :key="r.code" class="role-col"
                      :class="{ admin: r.code === 'admin' }">
                      <template v-if="r.code === 'admin'">
                        <el-icon color="#67c23a"><CircleCheck /></el-icon>
                      </template>
                      <el-checkbox
                        v-else
                        :model-value="r.permissions.includes(p.code)"
                        :disabled="!user.hasPerm('permission:edit')"
                        @change="(v: boolean | string | number | undefined) => togglePerm(r, p.code, !!v)"
                      />
                    </td>
                  </tr>
                </template>
              </tbody>
            </table>
          </div>
          <el-empty v-if="!loading && !activeRoles.length" description="暂无启用角色" :image-size="60" />
        </el-card>
      </el-tab-pane>

      <!-- 用户级覆盖 -->
      <el-tab-pane label="用户权限覆盖" name="user-override">
        <el-card shadow="never">
          <div class="filter-row">
            <el-select v-model="overrideUserId" filterable placeholder="选择用户" style="width: 240px" @change="loadOverrides">
              <el-option v-for="u in users" :key="u.id" :label="`${u.name}（${u.username}）`" :value="u.id" />
            </el-select>
            <el-button v-if="user.hasPerm('permission:edit')" type="primary" plain :disabled="!overrideUserId"
              :loading="savingOverrides" @click="saveOverrides">保存覆盖</el-button>
          </div>

          <div v-if="overrideData" class="mt-3">
            <el-table :data="overrideRows" size="small" border row-key="code" max-height="520">
              <el-table-column label="权限" min-width="220">
                <template #default="{ row }">
                  <span class="perm-label">{{ row.label }}</span>
                  <code class="perm-code">{{ row.code }}</code>
                </template>
              </el-table-column>
              <el-table-column label="覆盖状态" width="140">
                <template #default="{ row }">
                  <el-select v-model="row.grant_type" size="small" style="width: 110px">
                    <el-option label="继承角色" value="" />
                    <el-option label="授予" value="grant" />
                    <el-option label="拒绝" value="deny" />
                  </el-select>
                </template>
              </el-table-column>
              <el-table-column label="过期时间" width="150">
                <template #default="{ row }">
                  <el-date-picker v-model="row.expire_at" type="date" value-format="YYYY-MM-DD"
                    size="small" style="width: 130px" placeholder="永久" />
                </template>
              </el-table-column>
              <el-table-column label="备注" min-width="200">
                <template #default="{ row }">
                  <el-input v-model="row.remark" size="small" placeholder="备注（可选）" />
                </template>
              </el-table-column>
            </el-table>
          </div>
        </el-card>
      </el-tab-pane>
    </el-tabs>

    <!-- 角色新增/编辑 -->
    <el-dialog v-model="roleFormVisible" :title="roleForm.id ? '编辑角色' : '新增角色'" width="480px" destroy-on-close>
      <el-form ref="roleFormRef" :model="roleForm" label-width="90px">
        <el-form-item label="代码" prop="code" :rules="[{ required: true, message: '请输入', trigger: 'blur' }]">
          <el-input v-model="roleForm.code" :disabled="!!roleForm.id" placeholder="如 ops_manager（仅字母/数字/下划线）" />
        </el-form-item>
        <el-form-item label="名称" prop="name" :rules="[{ required: true, message: '请输入', trigger: 'blur' }]">
          <el-input v-model="roleForm.name" placeholder="如：运维主管" />
        </el-form-item>
        <el-form-item label="描述">
          <el-input v-model="roleForm.description" type="textarea" :rows="2" />
        </el-form-item>
        <el-form-item label="排序">
          <el-input-number v-model="roleForm.sort_order" :min="0" />
        </el-form-item>
        <el-form-item label="启用">
          <el-switch v-model="roleForm.is_active" active-text="启用" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="roleFormVisible = false">取消</el-button>
        <el-button type="primary" :loading="savingRole" @click="saveRole">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ElMessageBox } from 'element-plus/es/components/message-box/index'
import { ref, reactive, computed, onMounted } from 'vue'
import { Plus, CircleCheck } from '@element-plus/icons-vue'
import DataTable, { type DataColumn } from '@/components/DataTable.vue'
import {
  fetchRoles, createRole, updateRole, deleteRole, saveRolePermissions,
  fetchUserPermissions, saveUserPermissions, fetchUsers,
  type RoleListData, type RoleItem, type UserPermissionOverride,
} from '@/api/system'
import { useUserStore } from '@/stores/user'
import { useUiStore } from '@/stores/ui'
import { PERM_DOMAIN_LABELS } from '@/utils/labels'

const user = useUserStore()
const ui = useUiStore()
const activeTab = ref('matrix')
const data = ref<RoleListData | null>(null)
const loading = ref(false)
const saving = ref(new Set<string>())
const roleTableRef = ref()

// S7-1 角色表迁 DataTable（列配置 + 分页包装）
const roleColumns = computed<DataColumn[]>(() => [
  { key: 'name', label: '名称', minWidth: 120, asTitle: true },
  { key: 'code', label: '代码', minWidth: 120,
    render: (r) => `${r.code}${r.is_system ? '（内置）' : ''}` },
  { key: 'description', label: '描述', minWidth: 160, render: (r) => r.description || '-' },
  { key: 'sort_order', label: '排序', width: 70 },
  { key: 'is_active', label: '启用', width: 80, type: 'tag',
    tagMap: { true: 'success', false: 'info' }, render: (r) => (r.is_active ? '启用' : '停用') },
  { key: 'user_count', label: '用户数', width: 80 },
  { key: 'perm_count', label: '权限数', width: 80, render: (r) => r.permissions?.length ?? 0 },
  { key: 'actions', label: '操作', width: 130, type: 'action', fixed: 'right',
    actions: [
      { label: '编辑', type: 'primary', link: true, perm: 'permission:edit',
        onClick: (row) => openRoleEdit(row as unknown as RoleItem) },
      { label: '删除', type: 'danger', link: true, perm: 'permission:edit',
        disabled: (row: { is_system?: boolean }) => Boolean(row.is_system),
        onClick: (row) => onRoleDelete(row as unknown as RoleItem) },
    ] },
])

async function fetchRolePage(params: Record<string, unknown>) {
  const d = await fetchRoles()
  data.value = d
  const page = Number(params.page) || 1
  const page_size = Number(params.page_size) || 20
  const list = d.roles || []
  const start = (page - 1) * page_size
  return { items: list.slice(start, start + page_size), total: list.length,
    page, page_size }
}

const groupedPerms = computed(() => {
  const map = data.value?.perm_map || []
  const groups: Array<{ name: string; items: Array<{ code: string; label: string }> }> = []
  for (const p of map) {
    const domain = p.code.split(':')[0]
    let g = groups.find((x) => x.name === domain)
    if (!g) {
      g = { name: domain, items: [] }
      groups.push(g)
    }
    g.items.push(p)
  }
  return groups.map((g) => ({
    name: PERM_DOMAIN_LABELS[g.name] || g.name,
    items: g.items,
  }))
})

const roleRows = computed(() => data.value?.roles || [])
const activeRoles = computed(() => roleRows.value.filter((r) => r.is_active))

const roleFormVisible = ref(false)
const savingRole = ref(false)
const roleFormRef = ref()
const roleForm = reactive<Record<string, unknown>>({
  id: null, code: '', name: '', description: '', sort_order: 0, is_active: true,
})

const users = ref<Array<{ id: number; name: string; username: string }>>([])
const overrideUserId = ref<number | null>(null)
const overrideData = ref<{ user: { id: number; username: string; realname: string }; overrides: Record<string, UserPermissionOverride> } | null>(null)
const overrideRows = ref<Array<Record<string, unknown>>>([])
const savingOverrides = ref(false)

function load() {
  loading.value = true
  fetchRoles()
    .then((d) => { data.value = d })
    .catch(() => { /* toast */ })
    .finally(() => { loading.value = false })
}

async function togglePerm(role: RoleItem, code: string, on: boolean) {
  const key = `${role.id}:${code}`
  if (saving.value.has(key)) return
  saving.value.add(key)
  const prev = [...role.permissions]
  role.permissions = on ? [...prev, code] : prev.filter((c) => c !== code)
  try {
    await saveRolePermissions(role.id, role.permissions)
  } catch (e) {
    role.permissions = prev
    ui.toast((e as Error).message, 'error')
  } finally {
    saving.value.delete(key)
  }
}

function openRoleCreate() {
  Object.assign(roleForm, { id: null, code: '', name: '', description: '', sort_order: 0, is_active: true })
  roleFormVisible.value = true
}

function openRoleEdit(role: RoleItem) {
  Object.assign(roleForm, {
    id: role.id, code: role.code, name: role.name, description: role.description || '',
    sort_order: role.sort_order, is_active: !!role.is_active,
  })
  roleFormVisible.value = true
}

async function onRoleDelete(role: RoleItem) {
  const tip = role.user_count > 0
    ? `角色「${role.name}」还有 ${role.user_count} 个活跃用户，删除后这些用户将失去该角色权限，确定删除吗？`
    : `确定删除角色「${role.name}」吗？`
  try {
    await ElMessageBox.confirm(tip, '删除确认', { type: 'warning' })
  } catch { return }
  try {
    await deleteRole(role.id)
    ui.toast('角色已删除', 'success')
    load()
  } catch (e) {
    ui.toast((e as Error).message, 'error')
  }
}

async function saveRole() {
  try { await roleFormRef.value?.validate() } catch { return }
  savingRole.value = true
  try {
    const payload = {
      code: String(roleForm.code), name: String(roleForm.name),
      description: String(roleForm.description || ''), sort_order: Number(roleForm.sort_order || 0),
      is_active: !!roleForm.is_active,
    }
    if (roleForm.id) {
      await updateRole(roleForm.id as number, payload)
      ui.toast('已保存', 'success')
    } else {
      await createRole(payload)
      ui.toast('已创建', 'success')
    }
    roleFormVisible.value = false
    load()
  } catch (e) {
    ui.toast((e as Error).message, 'error')
  } finally {
    savingRole.value = false
  }
}

async function loadUsers() {
  try {
    const d = await fetchUsers()
    users.value = d.users.map((u) => ({ id: u.id, name: u.realname, username: u.username }))
  } catch { /* toast */ }
}

async function loadOverrides() {
  if (!overrideUserId.value) return
  try {
    const d = await fetchUserPermissions(overrideUserId.value)
    overrideData.value = d
    const map = d.perm_map
    overrideRows.value = map.map((p) => {
      const o = d.overrides[p.code]
      return {
        code: p.code, label: p.label,
        grant_type: o?.grant_type || '', expire_at: o?.expire_at || '', remark: o?.remark || '',
      }
    })
  } catch { /* toast */ }
}

async function saveOverrides() {
  if (!overrideUserId.value) return
  savingOverrides.value = true
  try {
    const overrides: Record<string, UserPermissionOverride> = {}
    for (const row of overrideRows.value) {
      if (row.grant_type) {
        overrides[row.code as string] = {
          grant_type: String(row.grant_type), expire_at: String(row.expire_at || ''), remark: String(row.remark || ''),
        }
      }
    }
    await saveUserPermissions(overrideUserId.value, overrides)
    ui.toast('权限覆盖已保存', 'success')
    loadOverrides()
  } catch (e) {
    ui.toast((e as Error).message, 'error')
  } finally {
    savingOverrides.value = false
  }
}

onMounted(() => {
  load()
  loadUsers()
})
</script>

<style scoped>
.matrix-scroll { overflow-x: auto; }
.perm-table { border-collapse: collapse; width: 100%; }
.perm-table th, .perm-table td {
  border: 1px solid var(--itsm-border); padding: 5px 8px; font-size: 12px;
}
.perm-table thead th { background: var(--el-fill-color-light); position: sticky; top: 0; z-index: 2; }
.role-col { text-align: center; min-width: 80px; }
.group-row td { background: var(--el-fill-color-light); font-weight: 600; }
.sticky-col { position: sticky; left: 0; background: var(--itsm-card-bg); z-index: 1; min-width: 240px; }
.perm-cell { display: flex; flex-direction: column; }
.perm-label { font-weight: 500; }
.perm-code { font-size: 10px; color: var(--itsm-text-muted); }
.filter-row { display: flex; gap: 8px; align-items: center; }
.mt-3 { margin-top: 12px; }
.ml-2 { margin-left: 8px; }
</style>
