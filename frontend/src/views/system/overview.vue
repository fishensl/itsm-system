<template>
  <div class="page-container">
    <div class="page-header">
      <h2 class="page-title">系统概览</h2>
      <div class="header-actions">
        <el-button size="small" type="primary" @click="onUiSwitch">
          {{ uiVersion === 'vue' ? '切换原界面（SSR）' : '切换新界面（Vue）' }}
        </el-button>
      </div>
    </div>

    <!-- 1. 资源监控 -->
    <h6 class="module-title"><el-icon><Odometer /></el-icon>资源监控</h6>
    <template v-if="resources?.available">
      <el-row :gutter="12">
        <el-col :xs="24" :sm="8">
          <div class="res-card">
            <div class="res-percent">{{ resources.cpu_percent }}%</div>
            <el-progress :percentage="Math.round(resources.cpu_percent ?? 0)" :stroke-width="8" :show-text="false" />
            <div class="res-sub">{{ resources.cpu_count }} 逻辑核心 / {{ resources.cpu_count_physical }} 物理核心</div>
          </div>
        </el-col>
        <el-col :xs="24" :sm="8">
          <div class="res-card">
            <div class="res-percent">{{ resources.memory_percent }}%</div>
            <el-progress :percentage="Math.round(resources.memory_percent ?? 0)" :stroke-width="8" :show-text="false" />
            <div class="res-sub">
              {{ resources.memory_used_gb }} / {{ resources.memory_total_gb }} GB · 可用 {{ resources.memory_available_gb }} GB
            </div>
          </div>
        </el-col>
        <el-col :xs="24" :sm="8">
          <div class="res-card">
            <div class="res-percent">{{ resources.disk_percent }}%</div>
            <el-progress :percentage="Math.round(resources.disk_percent ?? 0)" :stroke-width="8" :show-text="false" />
            <div class="res-sub">
              磁盘（系统盘）：{{ resources.disk_used_gb }} / {{ resources.disk_total_gb }} GB · 可用 {{ resources.disk_free_gb }} GB
            </div>
          </div>
        </el-col>
      </el-row>
    </template>
    <el-alert v-else type="warning" :closable="false" show-icon title="资源监控不可用"
      :description="resources?.error || '请安装 psutil'" />

    <!-- 2. 业务数据统计 -->
    <h6 class="module-title"><el-icon><DataAnalysis /></el-icon>业务数据统计</h6>
    <el-row :gutter="12">
      <el-col v-for="s in statCards" :key="s.label" :xs="12" :sm="6" :md="3">
        <div class="stat-card">
          <div class="stat-value">
            {{ s.value }}<small v-if="s.extra" class="stat-extra">/{{ s.extra }}</small>
          </div>
          <div class="stat-label">{{ s.label }}</div>
        </div>
      </el-col>
    </el-row>

    <!-- 3. 系统信息 + 数据库 + 最近用户 -->
    <el-row :gutter="12" class="mt-3">
      <el-col :xs="24" :md="8">
        <el-card shadow="never" class="info-card">
          <template #header><span class="card-title">系统信息</span></template>
          <el-descriptions :column="1" size="small" class="kv-desc">
            <el-descriptions-item label="操作系统">{{ sysInfo?.os_name }} {{ sysInfo?.os_release }}</el-descriptions-item>
            <el-descriptions-item label="架构">{{ sysInfo?.machine }}</el-descriptions-item>
            <el-descriptions-item label="主机名">{{ sysInfo?.hostname }}</el-descriptions-item>
            <el-descriptions-item label="Python">{{ sysInfo?.python_version }}</el-descriptions-item>
            <template v-if="resources?.available">
              <el-descriptions-item label="系统启动">{{ resources.boot_time }}</el-descriptions-item>
              <el-descriptions-item label="应用 PID">
                {{ resources.process_pid }} · 启动 {{ resources.process_start }}
              </el-descriptions-item>
              <el-descriptions-item label="应用内存">{{ resources.process_memory_mb }} MB</el-descriptions-item>
            </template>
          </el-descriptions>
        </el-card>
      </el-col>

      <el-col :xs="24" :md="8">
        <el-card shadow="never" class="info-card">
          <template #header><span class="card-title">数据库</span></template>
          <el-descriptions :column="1" size="small" class="kv-desc">
            <el-descriptions-item label="引擎">
              <el-tag size="small" type="info">{{ dbInfo?.engine }}</el-tag>
            </el-descriptions-item>
            <el-descriptions-item label="版本">{{ dbInfo?.version }}</el-descriptions-item>
            <el-descriptions-item v-if="dbInfo?.path" label="路径">{{ dbInfo.path }}</el-descriptions-item>
            <el-descriptions-item v-if="dbInfo?.size_mb" label="大小">{{ dbInfo.size_mb }} MB</el-descriptions-item>
            <el-descriptions-item label="系统版本">{{ overview?.version }}</el-descriptions-item>
          </el-descriptions>
        </el-card>
      </el-col>

      <el-col :xs="24" :md="8">
        <el-card shadow="never" class="info-card">
          <template #header>
            <div class="card-header-row">
              <span class="card-title">最近用户</span>
              <router-link class="all-link" to="/system/users">全部 ›</router-link>
            </div>
          </template>
          <div v-if="recentUsers.length" class="user-list">
            <div v-for="u in recentUsers" :key="u.username" class="user-row">
              <div class="user-name">
                <span class="user-main">{{ u.name }}</span>
                <span class="user-acc">@{{ u.username }}</span>
              </div>
              <el-tag size="small" :type="roleTag(u.role)">{{ roleLabel(u.role) }}</el-tag>
            </div>
          </div>
          <div v-else class="empty-tip">暂无用户</div>
        </el-card>
      </el-col>
    </el-row>

    <!-- 4. 组件版本 -->
    <h6 class="module-title mt-3"><el-icon><Box /></el-icon>组件版本</h6>
    <el-row :gutter="12">
      <el-col v-for="row in componentRows" :key="row.name" :xs="12" :sm="8" :md="6">
        <div class="comp-box">
          <span class="comp-name">{{ row.name }}</span>
          <code class="comp-ver">{{ row.version }}</code>
        </div>
      </el-col>
    </el-row>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { Odometer, DataAnalysis, Box } from '@element-plus/icons-vue'
import { fetchSystemOverview, fetchUiVersion, setUiVersion, type SystemOverview } from '@/api/system'
import { useUiStore } from '@/stores/ui'

const ui = useUiStore()
const overview = ref<SystemOverview | null>(null)
const uiVersion = ref<'vue' | 'ssr'>('ssr')

async function onUiSwitch() {
  const target = uiVersion.value === 'vue' ? 'ssr' : 'vue'
  try {
    const res = await setUiVersion(target)
    uiVersion.value = res.version
    ui.toast(`默认界面已切换为 ${res.version === 'vue' ? 'Vue' : 'SSR'}，刷新后生效`, 'success')
  } catch (e) {
    ui.toast((e as Error).message, 'error')
  }
}

const statCards = computed(() => {
  const s = overview.value?.stats || {}
  return [
    { label: '活跃用户', value: s.user_active ?? 0, extra: s.user_total ?? 0 },
    { label: '部门', value: s.department ?? 0 },
    { label: '客户', value: s.customer ?? 0 },
    { label: '设备', value: s.device ?? 0 },
    { label: '拓扑图', value: s.topology ?? 0 },
    { label: '巡检记录', value: s.inspection ?? 0 },
    { label: '工单', value: s.ticket ?? 0 },
  ]
})

const resources = computed(() => overview.value?.deploy?.resources)
const sysInfo = computed(() => overview.value?.deploy?.sys_info)
const dbInfo = computed(() => overview.value?.deploy?.db_info)
const recentUsers = computed(() => overview.value?.recent_users || [])

const componentRows = computed(() =>
  Object.entries(overview.value?.deploy?.components || {}).map(([name, version]) => ({ name, version })),
)

const ROLE_TAG: Record<string, 'danger' | 'primary' | 'warning' | 'info'> = {
  admin: 'danger', operator: 'primary', sales: 'warning', viewer: 'info',
}

function roleLabel(role: string) {
  return { admin: '管理员', operator: '运维', sales: '销售', viewer: '查看' }[role] || role
}

function roleTag(role: string) {
  return ROLE_TAG[role] || 'info'
}

onMounted(async () => {
  try {
    const [ov, uv] = await Promise.all([fetchSystemOverview(), fetchUiVersion()])
    overview.value = ov
    uiVersion.value = uv.version
  } catch { /* toast */ }
})
</script>

<style scoped>
.module-title {
  font-size: 13px;
  color: var(--itsm-text-muted);
  margin: 4px 0 10px;
  display: flex;
  align-items: center;
  gap: 6px;
}
.res-card {
  background: var(--itsm-card-bg);
  border: 1px solid var(--itsm-border);
  border-radius: 10px;
  padding: 14px;
  margin-bottom: 12px;
}
.res-percent {
  font-size: 24px;
  font-weight: 700;
  color: var(--el-color-primary);
  margin-bottom: 8px;
}
.res-sub {
  font-size: 12px;
  color: var(--itsm-text-muted);
  margin-top: 6px;
}
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
.stat-extra {
  font-size: 13px;
  color: var(--itsm-text-muted);
  font-weight: 400;
}
.stat-label {
  font-size: 12px;
  color: var(--itsm-text-muted);
  margin-top: 2px;
}
.mt-3 { margin-top: 12px; }
.card-title { font-weight: 600; font-size: 14px; }
.header-actions { display: flex; align-items: center; gap: 8px; }
.info-card { height: 100%; }
.kv-desc :deep(.el-descriptions__label) {
  width: 90px;
  color: var(--itsm-text-muted);
}
.card-header-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.all-link {
  font-size: 12px;
  color: var(--el-color-primary);
  text-decoration: none;
}
.user-list { display: flex; flex-direction: column; gap: 4px; }
.user-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 4px 2px;
}
.user-name { display: flex; align-items: baseline; gap: 6px; }
.user-main { font-weight: 600; font-size: 13px; }
.user-acc { font-size: 12px; color: var(--itsm-text-muted); }
.empty-tip {
  text-align: center;
  color: var(--itsm-text-muted);
  font-size: 12px;
  padding: 8px 0;
}
.comp-box {
  display: flex;
  justify-content: space-between;
  align-items: center;
  border: 1px solid var(--itsm-border);
  border-radius: 6px;
  padding: 6px 10px;
  margin-bottom: 10px;
}
.comp-name { font-size: 13px; }
.comp-ver {
  font-size: 12px;
  color: var(--el-color-primary);
  font-family: var(--font-mono, monospace);
}
</style>
