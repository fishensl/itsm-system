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

      <el-table :data="allRules" size="small" border>
        <el-table-column prop="label" label="通知类型" min-width="140" />
        <el-table-column prop="event_type" label="事件标识" min-width="180" />
        <el-table-column label="接收角色" min-width="200">
          <template #default="{ row }">
            <el-select v-model="row.roles" multiple collapse-tags clearable size="small" class="w-full"
              placeholder="选择接收角色（如销售/主管）">
              <el-option v-for="r in roleOptions" :key="r" :label="r" :value="r" />
            </el-select>
          </template>
        </el-table-column>
        <el-table-column label="接收用户" min-width="220">
          <template #default="{ row }">
            <el-select v-model="row.users" multiple filterable collapse-tags clearable size="small" class="w-full"
              placeholder="额外指定用户（如老板）">
              <el-option v-for="u in userOptions" :key="u.id" :label="u.realname || u.username" :value="u.id" />
            </el-select>
          </template>
        </el-table-column>
        <el-table-column label="启用" width="80" align="center">
          <template #default="{ row }">
            <el-switch v-model="row.is_enabled" />
          </template>
        </el-table-column>
        <el-table-column label="操作" width="90" align="center">
          <template #default="{ row }">
            <el-button size="small" type="primary" link @click="save(row)">保存</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import { useUiStore } from '@/stores/ui'
import {
  fetchNotifyRules, saveNotifyRule, fetchUsers, type UserItem,
  type NotifyRuleItem,
} from '@/api/system'

const ui = useUiStore()
const rules = ref<NotifyRuleItem[]>([])
const userOptions = ref<UserItem[]>([])
const roleOptions = ref<string[]>([])

/** 已种入规则 + 未种入事件类型 → 全量可配置列表 */
const allRules = computed(() => rules.value)

onMounted(async () => {
  try {
    const [r, u] = await Promise.all([fetchNotifyRules(), fetchUsers({ page: 1, page_size: 100 })])
    rules.value = r.rules
    userOptions.value = u.users
    const roles = u.roles as string[] | undefined
    roleOptions.value = roles || ['admin', 'operator', 'sales', 'viewer']
    // 未种入的事件类型补为默认关闭行
    for (const et of r.event_types) {
      if (!rules.value.some((x) => x.event_type === et.key)) {
        rules.value.push({ event_type: et.key, label: et.label, is_enabled: true, roles: [], users: [] })
      }
    }
  } catch { /* toast by interceptor */ }
})

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
