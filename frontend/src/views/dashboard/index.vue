<template>
  <div class="page-container">
    <!-- 统计卡（桌面一行 8 卡） -->
    <el-row :gutter="12" class="metric-row">
      <el-col v-for="m in data?.metrics || []" :key="m.label" :xs="12" :sm="8" :lg="3">
        <div class="metric-card" :class="{ 'metric-clickable': !!m.url }" @click="m.url && go(m.url)">
          <div class="metric-icon" :style="{ background: m.accent + '22', color: m.accent }">
            <el-icon :size="18"><component :is="m.icon" /></el-icon>
          </div>
          <div class="metric-body">
            <div class="metric-value">{{ m.value }}</div>
            <div class="metric-label">{{ m.label }}</div>
            <div class="metric-sub" :title="m.sub">{{ m.sub }}</div>
          </div>
          <el-icon v-if="m.url" class="metric-arrow" :size="13"><ArrowRight /></el-icon>
        </div>
      </el-col>
    </el-row>

    <!-- 我的待办 + 快捷入口（等高） -->
    <el-row :gutter="12" class="mt-3 equal-row">
      <el-col :xs="24" :md="14" class="equal-col">
        <el-card shadow="never" class="section-card">
          <template #header>
            <div class="section-header">
              <span>我的待办</span>
              <span class="section-count">{{ data?.my_tasks?.length || 0 }} 项</span>
            </div>
          </template>
          <div v-if="data?.my_tasks?.length" class="task-list equal-scroll">
            <div v-for="(t, i) in data.my_tasks" :key="i" class="task-item" @click="go(t.url)">
              <span class="task-type" :class="`task-type-${t.type_color}`">{{ t.type_label }}</span>
              <span class="task-title">{{ t.title }}</span>
              <span class="task-sub">{{ t.sub }}</span>
              <span class="task-time">{{ t.time }}</span>
            </div>
          </div>
          <el-empty v-else description="暂无待办任务" :image-size="60" />
        </el-card>
      </el-col>
      <el-col :xs="24" :md="10" class="equal-col">
        <el-card shadow="never" class="section-card">
          <template #header>
            <div class="section-header"><span>快捷入口</span></div>
          </template>
          <div class="quick-grid">
            <div v-for="q in data?.quick_entries || []" :key="q.url" class="quick-item" @click="go(q.url)">
              <el-icon :size="19" color="var(--itsm-primary)"><component :is="q.icon" /></el-icon>
              <div class="quick-title">{{ q.title }}</div>
              <div class="quick-sub">{{ q.sub }}</div>
            </div>
          </div>
        </el-card>

        <!-- 即将到期授权 -->
        <el-card v-if="data?.expiring_devices?.length" shadow="never" class="section-card mt-3">
          <template #header>
            <div class="section-header"><span>30 天内到期授权</span></div>
          </template>
          <div v-for="d in data.expiring_devices" :key="d.id" class="expiring-item">
            <span class="expiring-name">{{ d.device_name }}</span>
            <span class="expiring-cust">{{ d.customer_name }}</span>
            <el-tag size="small" :type="d.remaining_days < 0 ? 'danger' : 'warning'">
              {{ d.remaining_days < 0 ? `已过期 ${-d.remaining_days} 天` : `剩 ${d.remaining_days} 天` }}
            </el-tag>
          </div>
        </el-card>

        <!-- 即将到期客户（V28，仅客户管理者可见） -->
        <el-card v-if="data?.expiring_customers?.length" shadow="never" class="section-card mt-3">
          <template #header>
            <div class="section-header"><span>即将到期客户</span></div>
          </template>
          <div v-for="c in data.expiring_customers" :key="c.id" class="expiring-item" @click="go('/app/customers')">
            <span class="expiring-name">{{ c.name }}</span>
            <span class="expiring-cust">{{ c.contract_end_date }}</span>
            <el-tag size="small" :type="(c.remaining_days ?? 0) < 0 ? 'danger' : 'warning'">
              {{ (c.remaining_days ?? 0) < 0 ? `已过期 ${-(c.remaining_days ?? 0)} 天` : `剩 ${c.remaining_days} 天` }}
            </el-tag>
          </div>
        </el-card>
      </el-col>
    </el-row>

    <!-- 最近巡检 + 设备类型分布（等高） -->
    <el-row :gutter="12" class="mt-3 equal-row">
      <el-col :xs="24" :md="14" class="equal-col">
        <el-card shadow="never" class="section-card">
          <template #header>
            <div class="section-header"><span>最近巡检</span></div>
          </template>
          <div v-if="data?.recent_inspections?.length" class="task-list equal-scroll">
            <div v-for="r in data.recent_inspections" :key="r.id" class="task-item" @click="go(`/app/inspections/${r.id}`)">
              <span class="task-type task-type-info">巡检</span>
              <span class="task-title">{{ r.title }}</span>
              <span class="task-sub">{{ r.customer_name }}</span>
              <el-tag size="small" :type="OVERALL_TAG[r.overall_status] || 'info'">{{ r.overall_status }}</el-tag>
            </div>
          </div>
          <el-empty v-else description="暂无巡检记录" :image-size="60" />
        </el-card>
      </el-col>
      <el-col :xs="24" :md="10" class="equal-col">
        <el-card shadow="never" class="section-card">
          <template #header>
            <div class="section-header"><span>设备类型分布</span></div>
          </template>
          <div v-if="hasDeviceData" ref="pieRef" class="type-pie" />
          <el-empty v-else description="暂无设备" :image-size="60" />
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, watch, onBeforeUnmount, nextTick } from 'vue'
import { useRouter } from 'vue-router'
import { ArrowRight } from '@element-plus/icons-vue'
import * as echarts from 'echarts/core'
import { PieChart } from 'echarts/charts'
import { TooltipComponent, LegendComponent } from 'echarts/components'
import { SVGRenderer } from 'echarts/renderers'
import { fetchDashboard, type DashboardData } from '@/api/auth'
import { OVERALL_STATUS_TAG } from '@/utils/status'

echarts.use([PieChart, TooltipComponent, LegendComponent, SVGRenderer])

const OVERALL_TAG = OVERALL_STATUS_TAG
const router = useRouter()
const data = ref<DashboardData | null>(null)
const loading = ref(false)
const pieRef = ref<HTMLElement>()
let pieChart: echarts.ECharts | null = null

// 设备类型分布：前 8 类 + 其余合并「其他」
const hasDeviceData = computed(() => {
  const stats = data.value?.device_type_stats || []
  return stats.some(([, cnt]) => (cnt || 0) > 0)
})

const pieData = computed(() => {
  const stats = (data.value?.device_type_stats || []).filter(([, cnt]) => (cnt || 0) > 0)
  if (!stats.length) return []
  const top = stats.slice(0, 8).map(([name, cnt]) => ({ name, value: cnt }))
  const rest = stats.slice(8).reduce((s, [, cnt]) => s + (cnt || 0), 0)
  if (rest > 0) top.push({ name: '其他', value: rest })
  return top
})

function renderPie() {
  if (!pieRef.value || !pieData.value.length) return
  if (!pieChart) {
    pieChart = echarts.init(pieRef.value)
  }
  pieChart.setOption({
    tooltip: { trigger: 'item', formatter: '{b}：{c} 台（{d}%）' },
    legend: {
      orient: 'vertical',
      right: 4,
      top: 'middle',
      type: 'scroll',
      maxHeight: 180,
      textStyle: { fontSize: 12 },
    },
    series: [{
      type: 'pie',
      radius: ['42%', '70%'],
      center: ['36%', '50%'],
      avoidLabelOverlap: true,
      itemStyle: { borderRadius: 4, borderColor: 'var(--itsm-card-bg)', borderWidth: 1 },
      label: { show: false },
      data: pieData.value,
    }],
  })
}

function renderAll() {
  renderPie()
}

watch(pieData, () => nextTick(renderPie))

onMounted(async () => {
  loading.value = true
  try {
    data.value = await fetchDashboard()
  } catch {
    /* 错误提示由拦截器统一处理 */
  } finally {
    loading.value = false
  }
  nextTick(renderAll)
})

onBeforeUnmount(() => {
  if (pieChart) {
    pieChart.dispose()
    pieChart = null
  }
})

const go = (url: string) => {
  if (url.startsWith('/app')) {
    router.push(url.replace('/app', ''))
  } else {
    window.location.href = url
  }
}
</script>

<style scoped>
.metric-row {
  margin-bottom: 12px;
}
.metric-card {
  display: flex;
  gap: 10px;
  align-items: center;
  background: var(--itsm-card-bg);
  border: 1px solid var(--itsm-border);
  border-radius: 10px;
  padding: 10px 12px;
  margin-bottom: 12px;
  min-width: 0;
}
.metric-clickable {
  cursor: pointer;
  transition: border-color 0.15s, box-shadow 0.15s, transform 0.15s;
  position: relative;
}
.metric-clickable:hover {
  border-color: var(--itsm-primary);
  box-shadow: var(--itsm-shadow-sm);
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
  width: 34px;
  height: 34px;
  border-radius: 9px;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}
.metric-value {
  font-size: 18px;
  font-weight: 700;
  line-height: 1.2;
}
.metric-label {
  font-size: 12px;
  font-weight: 500;
  white-space: nowrap;
}
.metric-sub {
  font-size: 11px;
  color: var(--itsm-text-muted);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
/* 等高行 */
.equal-row {
  display: flex;
}
.equal-col {
  display: flex;
}
.section-card {
  margin-bottom: 12px;
  width: 100%;
  display: flex;
  flex-direction: column;
}
.section-card :deep(.el-card__body) {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
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
  color: var(--itsm-text-inverse);
}
.task-type-danger { background: var(--itsm-danger); }
.task-type-primary { background: var(--itsm-primary); }
.task-type-warning { background: var(--itsm-warning); }
.task-type-success { background: var(--itsm-success); }
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
  cursor: pointer;
}
.expiring-item:hover {
  background: var(--el-fill-color-light);
}
.expiring-name {
  font-weight: 500;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.expiring-cust {
  color: var(--itsm-text-muted);
  font-size: 12px;
  margin-right: auto;
}
.type-pie {
  height: 260px;
  width: 100%;
}
</style>
