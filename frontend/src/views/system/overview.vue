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
      <template #header>
        <span class="card-title">界面版本切换</span>
      </template>
      <el-alert type="info" :closable="false" show-icon
        title="切换「默认界面」：Vue（/app/* 新界面）或 SSR（原界面）。切换后 SSR 侧栏链接与首页入口跟随；可随时切回。" />
      <div class="mt-2">
        <el-radio-group v-model="uiVersion" @change="onUiVersionChange">
          <el-radio-button value="ssr">SSR（原界面）</el-radio-button>
          <el-radio-button value="vue">Vue（新界面）</el-radio-button>
        </el-radio-group>
        <span v-if="uiVersion === 'vue'" class="version-hint">
          已迁移 {{ migratedCount }} 个页面到 /app/*
        </span>
      </div>
    </el-card>

    <el-card shadow="never" class="mt-3">
      <template #header><span class="card-title">系统提示</span></template>
      <el-alert type="info" :closable="false" show-icon
        title="本页为 Vue 版系统概览；完整部署信息（CPU/内存/磁盘/组件版本）请在原系统概览页查看" />
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { fetchSystemOverview, fetchUiVersion, setUiVersion, type SystemOverview } from '@/api/system'
import { useUiStore } from '@/stores/ui'

const ui = useUiStore()
const overview = ref<SystemOverview | null>(null)
const uiVersion = ref<'vue' | 'ssr'>('ssr')
const migratedCount = ref(0)

async function onUiVersionChange(v: string | number | boolean | undefined) {
  try {
    const res = await setUiVersion(v as 'vue' | 'ssr')
    uiVersion.value = res.version
    ui.toast(`默认界面已切换为 ${res.version === 'vue' ? 'Vue' : 'SSR'}，刷新后生效`, 'success')
  } catch (e) {
    ui.toast((e as Error).message, 'error')
  }
}

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
    const [ov, uv] = await Promise.all([fetchSystemOverview(), fetchUiVersion()])
    overview.value = ov
    uiVersion.value = uv.version
    migratedCount.value = uv.vue_migrated_count
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
.version-hint { margin-left: 12px; color: var(--itsm-text-muted); font-size: 12px; }
</style>
