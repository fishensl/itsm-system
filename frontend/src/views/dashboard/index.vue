<template>
  <div class="page-container">
    <!-- 统计卡 -->
    <el-row
      :gutter="12"
      class="metric-row"
    >
      <el-col
        v-for="m in data?.metrics || []"
        :key="m.label"
        :xs="12"
        :sm="8"
        :md="4"
      >
        <div
          class="metric-card"
          :class="{ 'metric-clickable': !!m.url }"
          @click="m.url && go(m.url)"
        >
          <div
            class="metric-icon"
            :style="{ background: m.accent + '22', color: m.accent }"
          >
            <el-icon :size="20">
              <component :is="m.icon" />
            </el-icon>
          </div>
          <div class="metric-body">
            <div class="metric-value">
              {{ m.value }}
            </div>
            <div class="metric-label">
              {{ m.label }}
            </div>
            <div class="metric-sub">
              {{ m.sub }}
            </div>
          </div>
          <el-icon v-if="m.url" class="metric-arrow" :size="14">
            <ArrowRight />
          </el-icon>
        </div>
      </el-col>
    </el-row>

    <!-- 我的待办 + 快捷入口 -->
    <el-row
      :gutter="12"
      class="mt-3"
    >
      <el-col
        :xs="24"
        :md="14"
      >
        <el-card
          shadow="never"
          class="section-card"
        >
          <template #header>
            <div class="section-header">
              <span>我的待办</span>
              <span class="section-count">{{ data?.my_tasks?.length || 0 }} 项</span>
            </div>
          </template>
          <div
            v-if="data?.my_tasks?.length"
            class="task-list"
          >
            <div
              v-for="(t, i) in data.my_tasks"
              :key="i"
              class="task-item"
              @click="go(t.url)"
            >
              <span
                class="task-type"
                :class="`task-type-${t.type_color}`"
              >{{ t.type_label }}</span>
              <span class="task-title">{{ t.title }}</span>
              <span class="task-sub">{{ t.sub }}</span>
              <span class="task-time">{{ t.time }}</span>
            </div>
          </div>
          <el-empty
            v-else
            description="暂无待办任务"
            :image-size="60"
          />
        </el-card>
      </el-col>
      <el-col
        :xs="24"
        :md="10"
      >
        <el-card
          shadow="never"
          class="section-card"
        >
          <template #header>
            <div class="section-header">
              <span>快捷入口</span>
            </div>
          </template>
          <div class="quick-grid">
            <div
              v-for="q in data?.quick_entries || []"
              :key="q.url"
              class="quick-item"
              @click="go(q.url)"
            >
              <el-icon
                :size="20"
                color="#2563eb"
              >
                <component :is="q.icon" />
              </el-icon>
              <div class="quick-title">
                {{ q.title }}
              </div>
              <div class="quick-sub">
                {{ q.sub }}
              </div>
            </div>
          </div>
        </el-card>

        <!-- 即将到期授权 -->
        <el-card
          v-if="data?.expiring_devices?.length"
          shadow="never"
          class="section-card mt-3"
        >
          <template #header>
            <div class="section-header">
              <span>30 天内到期授权</span>
            </div>
          </template>
          <div
            v-for="d in data.expiring_devices"
            :key="d.id"
            class="expiring-item"
          >
            <span class="expiring-name">{{ d.device_name }}</span>
            <span class="expiring-cust">{{ d.customer_name }}</span>
            <el-tag
              size="small"
              :type="d.remaining_days < 0 ? 'danger' : 'warning'"
            >
              {{ d.remaining_days < 0 ? `已过期 ${-d.remaining_days} 天` : `剩 ${d.remaining_days} 天` }}
            </el-tag>
          </div>
        </el-card>
      </el-col>
    </el-row>

    <!-- 任务看板（工作台一部分；按角色自动匹配数据范围） -->
    <el-card v-if="user.hasPerm('task:schedule')" shadow="never" class="section-card mt-3">
      <template #header>
        <div class="section-header"><span>任务看板</span></div>
      </template>
      <TaskBoardPanel compact :show-filters="true" />
    </el-card>

    <!-- 最近巡检 + 设备类型分布 -->
    <el-row :gutter="12" class="mt-3">
      <el-col :xs="24" :md="14">
        <el-card shadow="never" class="section-card">
          <template #header>
            <div class="section-header"><span>最近巡检</span></div>
          </template>
          <div v-if="data?.recent_inspections?.length" class="task-list">
            <div v-for="r in data.recent_inspections" :key="r.id" class="task-item"
              @click="go(`/app/inspections/${r.id}`)">
              <span class="task-type task-type-info">巡检</span>
              <span class="task-title">{{ r.title }}</span>
              <span class="task-sub">{{ r.customer_name }}</span>
              <el-tag size="small" :type="OVERALL_TAG[r.overall_status] || 'info'">
                {{ r.overall_status }}
              </el-tag>
            </div>
          </div>
          <el-empty v-else description="暂无巡检记录" :image-size="60" />
        </el-card>
      </el-col>
      <el-col :xs="24" :md="10">
        <el-card shadow="never" class="section-card">
          <template #header>
            <div class="section-header"><span>设备类型分布</span></div>
          </template>
          <div v-if="data?.device_type_stats?.length" class="type-stats">
            <div v-for="[name, cnt] in data.device_type_stats" :key="name" class="type-stat-row">
              <span class="type-stat-name">{{ name }}</span>
              <el-progress :percentage="typePct(cnt)" :stroke-width="8" />
              <span class="type-stat-cnt">{{ cnt }}</span>
            </div>
          </div>
          <el-empty v-else description="暂无设备" :image-size="60" />
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { ArrowRight } from '@element-plus/icons-vue'
import { fetchDashboard, type DashboardData } from '@/api/auth'
import { OVERALL_STATUS_TAG } from '@/utils/status'
import { useUserStore } from '@/stores/user'
import TaskBoardPanel from '@/components/TaskBoardPanel.vue'

const OVERALL_TAG = OVERALL_STATUS_TAG
const router = useRouter()
const user = useUserStore()
const data = ref<DashboardData | null>(null)
const loading = ref(false)

const typePct = (cnt: number) => {
  const stats = data.value?.device_type_stats || []
  const total = stats.reduce((s, [, c]) => s + c, 0)
  if (!total) return 0
  return Math.round((cnt / total) * 100)
}

const go = (url: string) => {
  if (url.startsWith('/app')) {
    router.push(url.replace('/app', ''))
  } else {
    window.location.href = url
  }
}

onMounted(async () => {
  loading.value = true
  try {
    data.value = await fetchDashboard()
  } catch {
    /* 错误提示由拦截器统一处理 */
  } finally {
    loading.value = false
  }
})
</script>

<style scoped>
.metric-row {
  margin-bottom: 12px;
}
.metric-card {
  display: flex;
  gap: 12px;
  align-items: center;
  background: var(--itsm-card-bg);
  border: 1px solid var(--itsm-border);
  border-radius: 10px;
  padding: 14px;
  margin-bottom: 12px;
}
.metric-clickable {
  cursor: pointer;
  transition: border-color 0.15s, box-shadow 0.15s, transform 0.15s;
  position: relative;
}
.metric-clickable:hover {
  border-color: var(--itsm-primary);
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.08);
  transform: translateY(-1px);
}
.metric-arrow {
  margin-left: auto;
  color: var(--itsm-text-muted);
  flex-shrink: 0;
  transition: transform 0.15s;
}
.metric-clickable:hover .metric-arrow {
  color: var(--itsm-primary);
  transform: translateX(2px);
}
.metric-icon {
  width: 40px;
  height: 40px;
  border-radius: 10px;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}
.metric-value {
  font-size: 20px;
  font-weight: 700;
  line-height: 1.2;
}
.metric-label {
  font-size: 13px;
  font-weight: 500;
}
.metric-sub {
  font-size: 11px;
  color: var(--itsm-text-muted);
}
.section-card {
  margin-bottom: 12px;
}
.section-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-weight: 600;
  font-size: 14px;
}
.section-count {
  color: var(--itsm-text-muted);
  font-weight: 400;
  font-size: 12px;
}
.task-list {
  display: flex;
  flex-direction: column;
}
.task-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 9px 4px;
  border-bottom: 1px dashed var(--itsm-border);
  cursor: pointer;
  font-size: 13px;
}
.task-item:hover {
  background: var(--el-fill-color-light);
}
.task-type {
  flex-shrink: 0;
  font-size: 11px;
  padding: 1px 6px;
  border-radius: 4px;
  color: #fff;
}
.task-type-danger { background: #f56c6c; }
.task-type-primary { background: #409eff; }
.task-type-warning { background: #e6a23c; }
.task-type-success { background: #67c23a; }
.task-title {
  font-weight: 500;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.task-sub {
  color: var(--itsm-text-muted);
  font-size: 12px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  min-width: 0;
}
.task-time {
  margin-left: auto;
  color: var(--itsm-text-muted);
  font-size: 12px;
  flex-shrink: 0;
}
.quick-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 8px;
}
.quick-item {
  border: 1px solid var(--itsm-border);
  border-radius: 8px;
  padding: 10px;
  cursor: pointer;
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.quick-item:hover {
  border-color: var(--itsm-primary);
}
.quick-title {
  font-size: 13px;
  font-weight: 500;
}
.quick-sub {
  font-size: 11px;
  color: var(--itsm-text-muted);
}
.expiring-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 0;
  font-size: 13px;
}
.expiring-name {
  font-weight: 500;
}
.expiring-cust {
  color: var(--itsm-text-muted);
  font-size: 12px;
  margin-right: auto;
}
</style>
