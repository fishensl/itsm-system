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
        <el-input v-model="query.search" placeholder="搜索标题/文件名" clearable class="filter-search"
          @keyup.enter="reload" @clear="reload" />
        <el-button type="primary" plain :icon="Search" @click="reload">查询</el-button>
      </div>
    </el-card>

    <!-- tab 切换 -->
    <el-tabs v-model="tab" class="report-tabs" @tab-change="reload">
      <el-tab-pane label="全部" name="all" />
      <el-tab-pane label="巡检" name="inspection" />
      <el-tab-pane label="故障" name="fault" />
      <el-tab-pane label="工单" name="ticket" />
      <el-tab-pane label="报告文件" name="file" />
    </el-tabs>

    <!-- 统一列表（记录 + 报告文件，每行可下载报告） -->
    <DataTable
      ref="tableRef"
      :columns="columns"
      :fetch-data="fetchReportsData"
      :query="query"
      row-key="id"
      :column-settings="{ storageKey: 'cols_reports' }"
    />
  </div>
</template>

<script setup lang="ts">
import { ElMessageBox } from 'element-plus/es/components/message-box/index'
import { ref, reactive, computed, onMounted, h, type VNode } from 'vue'
import { Search, Download, Delete } from '@element-plus/icons-vue'
import DataTable, { type DataColumn } from '@/components/DataTable.vue'
import { http } from '@/utils/request'
import type { PageResult } from '@/types'
import {
  fetchReports, REPORT_TYPE_TAG, REPORT_TYPE_MAP, type ReportTab,
} from '@/api/reports'
import { fetchCustomers } from '@/api/customers'
import { useUiStore } from '@/stores/ui'

const ui = useUiStore()

const tab = ref<ReportTab>('all')
const query = reactive<Record<string, unknown>>({
  date_from: '', date_to: '', customer_id: undefined, search: '',
})
const stats = reactive<{ customers: number; total: number }>({ customers: 0, total: 0 })
const tableRef = ref()

const customers = ref<{ id: number; name: string }[]>([])

/** 状态徽章颜色：巡检审核状态 / 故障结果 / 工单状态 / 文件报告类型 */
const STATUS_TAG: Record<string, 'primary' | 'success' | 'warning' | 'danger' | 'info'> = {
  '已通过': 'success', '已退回': 'danger', '待审核': 'warning', '草稿': 'info',
  '已解决': 'success', '待观察': 'warning', '未解决': 'danger',
  '已完成': 'success', '已关闭': 'info', '处理中': 'primary', '待验收': 'primary',
  '待派单': 'warning', '待接单': 'warning',
  '巡检报告': 'primary', '故障报告': 'danger',
}

function reportCell(row: Record<string, any>): string | VNode {
  if (!row.has_report || !row.report_url) return h('span', { class: 'report-none' }, '无')
  return h('div', { class: 'report-cell' }, [
    h('span', { class: 'report-name', title: row.report_name }, row.report_name),
    h('span', { class: 'report-size' }, row.size_display ? `（${row.size_display}）` : ''),
    h('a', { class: 'report-download', href: row.report_url, target: '_blank' }, '下载'),
  ])
}

const columns = computed<DataColumn[]>(() => [
  { key: 'type', label: '类型', width: 90, type: 'tag', asTag: true,
    tagMap: REPORT_TYPE_TAG, valueMap: REPORT_TYPE_MAP },
  { key: 'title', label: '标题 / 文件名', minWidth: 200, asTitle: true, type: 'link',
    link: (r) => (r.type === 'inspection'
      ? `/app/inspections/${r.id}`
      : (r.type === 'ticket' ? `/app/tickets/${r.id}` : '')) },
  { key: 'customer_name', label: '客户', minWidth: 100 },
  { key: 'date', label: '日期', width: 140 },
  { key: 'status', label: '状态', width: 90, type: 'tag', valueMap: { '': '—' }, tagMap: STATUS_TAG },
  { key: 'report', label: '报告文件', minWidth: 180, type: 'custom', render: (row) => reportCell(row) },
  { key: 'actions', label: '操作', width: 110, type: 'action', fixed: 'right',
    actions: [
      { label: '下载报告', type: 'primary', link: true, icon: 'Download', perm: 'report:view',
        disabled: (row) => !row.has_report,
        onClick: (row) => downloadReport(row as Record<string, unknown>) },
      { label: '删除', type: 'danger', link: true, icon: 'Delete', perm: 'report:delete',
        disabled: (row) => row.type !== 'file' || !row.deletable,
        onClick: (row) => deleteFile(row as Record<string, unknown>) },
    ] },
])

/** DataTable 适配：分页拉取统一列表，同步页头统计 */
async function fetchReportsData(params: Record<string, any>): Promise<PageResult<Record<string, any>>> {
  const data = await fetchReports({
    tab: tab.value,
    date_from: (params.date_from as string) || undefined,
    date_to: (params.date_to as string) || undefined,
    customer_id: params.customer_id as number | undefined,
    search: (params.search as string) || undefined,
    page: params.page,
    page_size: params.page_size,
  })
  stats.customers = data.stats.customers
  stats.total = data.stats.total
  return { items: data.items, total: data.total, page: params.page, page_size: params.page_size }
}

function reload() { tableRef.value?.refresh() }

function downloadReport(row: Record<string, unknown>) {
  if (row.report_url) window.open(row.report_url as string, '_blank')
}

async function deleteFile(row: Record<string, unknown>) {
  const filename = row.title as string
  try {
    await ElMessageBox.confirm(`确定删除报告「${filename}」吗？`, '删除确认', { type: 'warning' })
  } catch { return }
  try {
    // SSR 删除端点返回 redirect HTML，用裸 axios 发送（响应体不解析）
    await http.post(`/reports/delete/${encodeURIComponent(filename)}`)
    ui.toast('已删除', 'success')
    reload()
  } catch (e) {
    ui.toast((e as Error).message, 'error')
  }
}

onMounted(() => {
  fetchCustomers({ page: 1, page_size: 100 }).then((d) => {
    customers.value = d.items.map((c) => ({ id: c.id, name: c.name }))
  }).catch(() => {})
})
</script>

<style scoped>
.filter-card { margin-bottom: 12px; }
.filter-row { display: flex; gap: 8px; flex-wrap: wrap; align-items: center; }
.filter-item { width: 150px; max-width: 100%; }
.filter-search { width: 180px; max-width: 100%; }
.header-actions { display: flex; gap: 8px; flex-wrap: wrap; align-items: center; }
.report-tabs { margin-bottom: 8px; }
.report-cell { display: flex; align-items: center; gap: 6px; flex-wrap: wrap; }
.report-name { font-family: Consolas, monospace; font-size: 12px; word-break: break-all; }
.report-size { color: var(--itsm-text-muted); font-size: 12px; }
.report-download { color: var(--el-color-primary); font-size: 12px; }
.report-none { color: var(--itsm-text-muted); font-size: 12px; }
</style>
