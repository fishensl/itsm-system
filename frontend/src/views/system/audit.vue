<template>
  <div class="page-container">
    <div class="page-header">
      <h2 class="page-title">操作审计日志</h2>
    </div>

    <el-card shadow="never" class="filter-card">
      <div class="filter-row">
        <el-input v-model="query.username" placeholder="操作人" clearable class="filter-item"
          @keyup.enter="reload" @clear="reload" />
        <el-select v-model="query.action" placeholder="操作" clearable filterable class="filter-item"
          @change="reload">
          <el-option v-for="a in dicts?.actions || []" :key="a" :label="a" :value="a" />
        </el-select>
        <el-select v-model="query.target_type" placeholder="对象类型" clearable class="filter-item"
          @change="reload">
          <el-option v-for="t in dicts?.target_types || []" :key="t" :label="t" :value="t" />
        </el-select>
        <el-date-picker v-model="dateRange" type="daterange" value-format="YYYY-MM-DD"
          start-placeholder="开始日期" end-placeholder="结束日期" class="filter-date" @change="reload" />
        <el-button type="primary" plain :icon="Search" @click="reload">查询</el-button>
      </div>
    </el-card>

    <DataTable
      ref="tableRef"
      :columns="columns"
      :fetch-data="fetchLogs"
      :query="tableQuery"
      row-key="id"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onMounted } from 'vue'
import { Search } from '@element-plus/icons-vue'
import DataTable, { type DataColumn } from '@/components/DataTable.vue'
import { fetchAuditLogs, fetchAuditDicts } from '@/api/system'

const dicts = ref<{ actions: string[]; target_types: string[] } | null>(null)
const dateRange = ref<[string, string] | null>(null)
const tableRef = ref()

const query = reactive<Record<string, unknown>>({ username: '', action: '', target_type: '' })

const tableQuery = computed(() => ({
  ...query,
  date_from: dateRange.value?.[0] || '',
  date_to: dateRange.value?.[1] || '',
}))

const fetchLogs = (params: Record<string, unknown>) =>
  fetchAuditLogs(params as Record<string, string | number>)

const columns = computed<DataColumn[]>(() => [
  { key: 'created_at', label: '时间', width: 150 },
  { key: 'username', label: '操作人', width: 100, asTitle: true },
  { key: 'action', label: '操作', width: 130, type: 'tag' },
  { key: 'target_type', label: '对象', width: 90 },
  { key: 'detail', label: '详情', minWidth: 220 },
  { key: 'ip', label: 'IP', width: 130 },
])

function reload() { tableRef.value?.refresh() }

onMounted(() => {
  fetchAuditDicts().then((d) => (dicts.value = d))
})
</script>

<style scoped>
.filter-card { margin-bottom: 12px; }
.filter-row { display: flex; gap: 8px; flex-wrap: wrap; align-items: center; }
.filter-item { width: 150px; max-width: 100%; }
.filter-date { width: 260px; max-width: 100%; }
</style>
