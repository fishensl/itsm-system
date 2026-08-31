<template>
  <div class="page-container">
    <div class="page-header">
      <h2 class="page-title">通知规则</h2>
      <el-button v-if="user.hasPerm('notify:edit')" type="primary"
        :loading="saving" :disabled="!dirty" @click="saveAll">
        保存全部规则
      </el-button>
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
            placeholder="选择接收角色（如销售/主管）" @change="dirty = true">
            <el-option v-for="r in roleOptions" :key="r.code" :label="r.name" :value="r.code" />
          </el-select>
        </template>
        <template #cell-users="{ row }">
          <el-select v-model="row.users" multiple filterable collapse-tags clearable size="small" class="w-full"
            placeholder="额外指定用户（如老板）" @change="dirty = true">
            <el-option v-for="u in userOptions" :key="u.id" :label="u.name" :value="u.id" />
          </el-select>
        </template>
        <template #cell-is_enabled="{ row }">
          <el-switch v-model="row.is_enabled" @change="dirty = true" />
        </template>
      </DataTable>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { useUiStore } from '@/stores/ui'
import { useUserStore } from '@/stores/user'
import {
  fetchNotifyRules, saveNotifyRules, type NotifyRuleItem,
} from '@/api/system'
import { entityFieldLabel, fetchEntityMeta, type EntityMeta } from '@/api/meta'
import DataTable, { type DataColumn } from '@/components/DataTable.vue'

const ui = useUiStore()
const user = useUserStore()
const metadata = ref<EntityMeta>()
const userOptions = ref<Array<{ id: number; name: string }>>([])
const roleOptions = ref<Array<{ code: string; name: string }>>([])
const rules = ref<NotifyRuleItem[]>([])
const saving = ref(false)
const dirty = ref(false)

function label(key: string, fallback: string) {
  return entityFieldLabel(metadata.value, key, fallback, 'list')
}

const columns = computed<DataColumn[]>(() => [
  { key: 'label', label: label('label', '通知类型'), minWidth: 140, asTitle: true },
  { key: 'event_type', label: label('event_type', '事件标识'), minWidth: 180 },
  { key: 'roles', label: label('roles', '接收角色'), minWidth: 200, ellipsis: false },
  { key: 'users', label: label('users', '接收用户'), minWidth: 220, ellipsis: false },
  { key: 'is_enabled', label: label('is_enabled', '启用'), width: 80, align: 'center' },
])

async function fetchPage(params: Record<string, unknown>) {
  const [result, meta] = await Promise.all([
    fetchNotifyRules(), fetchEntityMeta('notify_rule'),
  ])
  metadata.value = meta
  userOptions.value = result.user_options
  roleOptions.value = result.role_options
  const rows = result.rules.map((item) => ({ ...item, roles: [...item.roles], users: [...item.users] }))
  for (const eventType of result.event_types) {
    if (!rows.some((item) => item.event_type === eventType.key)) {
      rows.push({ event_type: eventType.key, label: eventType.label,
        is_enabled: true, roles: [], users: [] })
    }
  }
  rules.value = rows
  dirty.value = false
  const page = Number(params.page) || 1
  const page_size = Number(params.page_size) || 20
  const start = (page - 1) * page_size
  return { items: rows.slice(start, start + page_size), total: rows.length, page, page_size }
}

async function saveAll() {
  saving.value = true
  try {
    const result = await saveNotifyRules(rules.value)
    dirty.value = false
    ui.toast(`已统一保存 ${result.count} 条通知规则`, 'success')
  } catch (e) {
    ui.toast((e as Error).message, 'error')
  } finally {
    saving.value = false
  }
}
</script>

<style scoped>
.card-header { display: flex; justify-content: space-between; align-items: center; }
.w-full { width: 100%; }
</style>
