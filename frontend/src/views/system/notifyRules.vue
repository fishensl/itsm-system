<template>
  <div class="page-container">
    <div class="page-header">
      <h2 class="page-title">通知规则</h2>
    </div>

    <el-card shadow="never">
      <template #header>
        <div class="card-header">
          <span>事件 → 接收对象（Zabbix 风格；与渠道解耦，推送时发往全部启用渠道）</span>
        </div>
      </template>

      <DataTable
        :columns="columns"
        :fetch-data="fetchPage"
        row-key="event_type"
        empty-text="暂无通知规则"
        :column-settings="{ storageKey: 'cols_notify_rules' }"
      >
        <template #cell-roles="{ row }">
          <el-select v-model="row.roles" multiple collapse-tags clearable size="small" class="w-full"
            placeholder="选择接收角色（如销售/主管）">
            <el-option v-for="r in roleOptions" :key="r" :label="r" :value="r" />
          </el-select>
        </template>
        <template #cell-users="{ row }">
          <el-select v-model="row.users" multiple filterable collapse-tags clearable size="small" class="w-full"
            placeholder="额外指定用户（如老板）">
            <el-option v-for="u in userOptions" :key="u.id" :label="u.realname || u.username" :value="u.id" />
          </el-select>
        </template>
        <template #cell-is_enabled="{ row }">
          <el-switch v-model="row.is_enabled" />
        </template>
      </DataTable>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { useUiStore } from '@/stores/ui'
import {
  fetchNotifyRules, saveNotifyRule, fetchUsers, type UserItem,
  type NotifyRuleItem,
} from '@/api/system'
import { entityFieldLabel, fetchEntityMeta, type EntityMeta } from '@/api/meta'
import DataTable, { type DataColumn } from '@/components/DataTable.vue'

const ui = useUiStore()
const metadata = ref<EntityMeta>()
const userOptions = ref<UserItem[]>([])
const roleOptions = ref<string[]>([])

function label(key: string, fallback: string) {
  return entityFieldLabel(metadata.value, key, fallback, 'list')
}

const columns = computed<DataColumn[]>(() => [
  { key: 'label', label: label('label', '通知类型'), minWidth: 140, asTitle: true },
  { key: 'event_type', label: label('event_type', '事件标识'), minWidth: 180 },
  { key: 'roles', label: label('roles', '接收角色'), minWidth: 200, ellipsis: false },
  { key: 'users', label: label('users', '接收用户'), minWidth: 220, ellipsis: false },
  { key: 'is_enabled', label: label('is_enabled', '启用'), width: 80, align: 'center' },
  { key: 'actions', label: '操作', width: 90, type: 'action', fixed: 'right', actions: [
    { label: '保存', type: 'primary', link: true,
      onClick: (row) => save(row as unknown as NotifyRuleItem) },
  ] },
])

async function fetchPage(params: Record<string, unknown>) {
  const [result, users, meta] = await Promise.all([
    fetchNotifyRules(), fetchUsers({ page: 1, page_size: 100 }), fetchEntityMeta('notify_rule'),
  ])
  metadata.value = meta
  userOptions.value = users.users
  roleOptions.value = (users.roles as string[] | undefined) || ['admin', 'operator', 'sales', 'viewer']
  const rows = [...result.rules]
  for (const eventType of result.event_types) {
    if (!rows.some((item) => item.event_type === eventType.key)) {
      rows.push({ event_type: eventType.key, label: eventType.label,
        is_enabled: true, roles: [], users: [] })
    }
  }
  const page = Number(params.page) || 1
  const page_size = Number(params.page_size) || 20
  const start = (page - 1) * page_size
  return { items: rows.slice(start, start + page_size), total: rows.length, page, page_size }
}

async function save(row: NotifyRuleItem) {
  try {
    await saveNotifyRule({
      event_type: row.event_type,
      is_enabled: row.is_enabled,
      roles: row.roles,
      users: row.users,
    })
    ui.toast(`规则「${row.label}」已保存`, 'success')
  } catch (e) {
    ui.toast((e as Error).message, 'error')
  }
}
</script>

<style scoped>
.card-header { display: flex; justify-content: space-between; align-items: center; }
.w-full { width: 100%; }
</style>
