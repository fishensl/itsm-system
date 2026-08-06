<template>
  <div class="page-container">
    <div class="page-header">
      <h2 class="page-title">报告中心</h2>
      <div class="header-actions">
        <el-tag size="small" effect="plain">覆盖客户 {{ stats.customers }}</el-tag>
        <el-tag size="small" effect="plain" type="primary">记录总数 {{ stats.total }}</el-tag>
      </div>
    </div>

    <!-- 筛选 -->
    <el-card shadow="never" class="filter-card">
      <div class="filter-row">
        <el-date-picker v-model="query.date_from" type="date" value-format="YYYY-MM-DD" placeholder="开始日期"
          class="filter-item date-item" @change="reload" />
        <el-date-picker v-model="query.date_to" type="date" value-format="YYYY-MM-DD" placeholder="结束日期"
          class="filter-item date-item" @change="reload" />
        <el-select v-model="query.customer_id" placeholder="客户" clearable filterable class="filter-item"
          @change="reload">
          <el-option v-for="c in customers" :key="c.id" :label="c.name" :value="c.id" />
        </el-select>
        <el-button type="primary" plain :icon="Search" @click="reload">查询</el-button>
      </div>
    </el-card>

    <!-- tab 切换 -->
    <el-tabs v-model="tab" class="report-tabs" @tab-change="reload">
      <el-tab-pane label="全部" name="all" />
      <el-tab-pane label="巡检" name="inspection" />
      <el-tab-pane label="故障" name="fault" />
      <el-tab-pane label="工单" name="ticket" />
      <el-tab-pane label="文件" name="file" />
    </el-tabs>

    <!-- 客户分桶 -->
    <div v-loading="loading">
      <el-collapse v-model="openPanels">
        <el-collapse-item v-for="(bucket, i) in dataOrder" :key="i" :name="i">
          <template #title>
            <div class="bucket-title">
              <span class="bucket-name">{{ bucket.name }}</span>
              <span class="bucket-badges">
                <el-tag v-if="bucket.counts.inspection" size="small" type="primary">巡检 {{ bucket.counts.inspection }}</el-tag>
                <el-tag v-if="bucket.counts.fault" size="small" type="danger">故障 {{ bucket.counts.fault }}</el-tag>
                <el-tag v-if="bucket.counts.ticket" size="small" type="warning">工单 {{ bucket.counts.ticket }}</el-tag>
                <el-tag v-if="bucket.counts.file" size="small" type="success">报告 {{ bucket.counts.file }}</el-tag>
                <el-tag v-else size="small" type="info">无报告</el-tag>
              </span>
            </div>
          </template>

          <!-- 巡检 -->
          <template v-if="bucket.items.inspection.length">
            <div class="bucket-section-label">巡检记录</div>
            <div v-for="item in bucket.items.inspection" :key="'i' + item.id" class="record-row">
              <span class="record-title">{{ item.title }}</span>
              <span class="record-meta">{{ item.inspection_date || '-' }}</span>
            </div>
          </template>

          <!-- 故障 -->
          <template v-if="bucket.items.fault.length">
            <div class="bucket-section-label">故障记录</div>
            <div v-for="item in bucket.items.fault" :key="'f' + item.id" class="record-row">
              <span class="record-title">{{ item.title }}</span>
              <span class="record-meta">
                {{ item.fault_time || '-' }}
                <el-tag v-if="item.result" size="small" :type="FAULT_RESULT_TAG[item.result] || 'danger'">
                  {{ item.result }}
                </el-tag>
              </span>
            </div>
          </template>

          <!-- 工单 -->
          <template v-if="bucket.items.ticket.length">
            <div class="bucket-section-label">工单记录</div>
            <div v-for="item in bucket.items.ticket" :key="'t' + item.id" class="record-row">
              <span class="record-title">{{ item.number }} · {{ item.title }}</span>
              <span class="record-meta">{{ item.created_at || '-' }}</span>
            </div>
          </template>

          <!-- 文件报告 -->
          <template v-if="bucket.items.file.length">
            <div class="bucket-section-label">报告文件</div>
            <div v-for="item in bucket.items.file" :key="item.filename" class="record-row">
              <span class="record-title file-name">{{ item.filename }}</span>
              <span class="record-meta">
                {{ item.type }} · {{ item.size_display }} · {{ item.create_time }}
                <el-button size="small" link type="primary" :icon="Download"
                  @click="downloadFile(item.filename)">下载</el-button>
                <el-button v-if="user.hasPerm('report:delete')" size="small" link type="danger"
                  :icon="Delete" @click="deleteFile(item.filename)">删除</el-button>
              </span>
            </div>
          </template>

          <el-empty v-if="!bucket.items.inspection.length && !bucket.items.fault.length
            && !bucket.items.ticket.length && !bucket.items.file.length"
            description="该客户暂无记录" :image-size="40" />
        </el-collapse-item>
      </el-collapse>
      <el-empty v-if="!loading && dataOrder.length === 0" description="暂无数据" :image-size="80" />
    </div>
  </div>
</template>

<script setup lang="ts">
import { ElMessageBox } from 'element-plus/es/components/message-box/index'
import { ref, reactive, onMounted, watch } from 'vue'
import { Search, Download, Delete } from '@element-plus/icons-vue'
import request, { http } from '@/utils/request'
import {
  fetchReports, type ReportTab, type ReportBucket,
} from '@/api/reports'
import { fetchCustomers } from '@/api/customers'
import { FAULT_RESULT_TAG } from '@/api/faults'
import { useUserStore } from '@/stores/user'
import { useUiStore } from '@/stores/ui'

const user = useUserStore()
const ui = useUiStore()

const tab = ref<ReportTab>('all')
const query = reactive<Record<string, unknown>>({ date_from: '', date_to: '', customer_id: undefined })
const dataOrder = ref<ReportBucket[]>([])
const stats = reactive<{ customers: number; total: number }>({ customers: 0, total: 0 })
const loading = ref(false)
const openPanels = ref<number[]>([])

const customers = ref<{ id: number; name: string }[]>([])

async function load() {
  loading.value = true
  try {
    const data = await fetchReports({
      tab: tab.value,
      date_from: (query.date_from as string) || undefined,
      date_to: (query.date_to as string) || undefined,
      customer_id: query.customer_id as number | undefined,
    })
    dataOrder.value = data.data_order
    const s = data.tab_stats[tab.value]
    stats.customers = s?.customers ?? 0
    stats.total = s?.total ?? 0
  } catch {
    /* 拦截器已提示 */
  } finally {
    loading.value = false
  }
}

function reload() { load() }

function downloadFile(filename: string) {
  window.open(`/reports/${encodeURIComponent(filename)}`, '_blank')
}

async function deleteFile(filename: string) {
  try {
    await ElMessageBox.confirm(`确定删除报告「${filename}」吗？`, '删除确认', { type: 'warning' })
  } catch { return }
  try {
    // SSR 删除端点返回 redirect HTML，用裸 axios 发送（响应体不解析）
    await http.post(`/reports/delete/${encodeURIComponent(filename)}`)
    ui.toast('已删除', 'success')
    load()
  } catch (e) {
    ui.toast((e as Error).message, 'error')
  }
}

onMounted(() => {
  load()
  fetchCustomers({ page: 1, page_size: 100 }).then((d) => {
    customers.value = d.items.map((c) => ({ id: c.id, name: c.name }))
  }).catch(() => {})
})

watch(tab, () => { openPanels.value = [] })
</script>

<style scoped>
.filter-card { margin-bottom: 12px; }
.filter-row { display: flex; gap: 8px; flex-wrap: wrap; align-items: center; }
.filter-item { width: 150px; max-width: 100%; }
.header-actions { display: flex; gap: 8px; flex-wrap: wrap; align-items: center; }
.report-tabs { margin-bottom: 8px; }
.bucket-title { display: flex; align-items: center; justify-content: space-between; gap: 12px; width: 100%; padding-right: 12px; }
.bucket-name { font-weight: 600; }
.bucket-badges { display: flex; gap: 6px; flex-wrap: wrap; }
.bucket-section-label { font-size: 12px; color: var(--itsm-text-muted); margin: 8px 0 4px; }
.record-row { display: flex; align-items: center; justify-content: space-between; gap: 12px; font-size: 13px; padding: 6px 4px; border-bottom: 1px dashed var(--itsm-border); flex-wrap: wrap; }
.record-title { word-break: break-all; }
.file-name { font-family: Consolas, monospace; font-size: 12px; }
.record-meta { color: var(--itsm-text-muted); font-size: 12px; display: flex; align-items: center; gap: 6px; flex-shrink: 0; }
</style>
