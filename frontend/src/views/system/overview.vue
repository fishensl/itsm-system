<template>
  <div class="page-container">
    <div class="page-header">
      <h2 class="page-title">系统概览</h2>
      <el-tag v-if="overview" type="info">{{ overview.version }}</el-tag>
    </div>

    <el-row :gutter="12">
      <el-col v-for="s in statCards" :key="s.label" :xs="12" :sm="8" :md="4">
        <div class="stat-card">
          <div class="stat-value">{{ s.value }}</div>
          <div class="stat-label">{{ s.label }}</div>
        </div>
      </el-col>
    </el-row>

    <el-card shadow="never" class="mt-3">
      <template #header><span class="card-title">系统提示</span></template>
      <el-alert type="info" :closable="false" show-icon
        title="本页为 Vue 版系统概览；完整部署信息（CPU/内存/磁盘/组件版本）请在原系统概览页查看" />
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { fetchSystemOverview, type SystemOverview } from '@/api/system'

const overview = ref<SystemOverview | null>(null)

const statCards = computed(() => {
  const s = overview.value?.stats || {}
  return [
    { label: '用户', value: s.user ?? 0 },
    { label: '部门', value: s.department ?? 0 },
    { label: '客户', value: s.customer ?? 0 },
    { label: '设备', value: s.device ?? 0 },
    { label: '工单', value: s.ticket ?? 0 },
    { label: '巡检', value: s.inspection ?? 0 },
    { label: '知识库', value: s.kb ?? 0 },
    { label: '备件', value: s.spare ?? 0 },
    { label: '拓扑', value: s.topology ?? 0 },
    { label: '未读通知', value: s.notification_unread ?? 0 },
    { label: '审计记录', value: s.audit_today ?? 0 },
  ]
})

onMounted(async () => {
  try {
    overview.value = await fetchSystemOverview()
  } catch { /* toast */ }
})
</script>

<style scoped>
.stat-card {
  background: var(--itsm-card-bg);
  border: 1px solid var(--itsm-border);
  border-radius: 10px;
  padding: 14px;
  margin-bottom: 12px;
  text-align: center;
}
.stat-value {
  font-size: 22px;
  font-weight: 700;
  color: var(--el-color-primary);
}
.stat-label {
  font-size: 12px;
  color: var(--itsm-text-muted);
  margin-top: 2px;
}
.mt-3 { margin-top: 12px; }
.card-title { font-weight: 600; font-size: 14px; }
</style>
