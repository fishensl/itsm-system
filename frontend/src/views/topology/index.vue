<template>
  <div class="page-container">
    <div class="page-header">
      <h2 class="page-title">拓扑图</h2>
    </div>

    <!-- 筛选 -->
    <el-card shadow="never" class="filter-card">
      <div class="filter-row">
        <el-input v-model="query.search" placeholder="搜索名称 / 描述" clearable class="filter-search"
          @keyup.enter="reload" @clear="reload" />
        <el-button type="primary" plain :icon="Search" @click="reload">查询</el-button>
      </div>
    </el-card>

    <!-- 列表 -->
    <DataTable
      ref="tableRef"
      :columns="columns"
      :fetch-data="fetchTopologies"
      :query="query"
      row-key="id"
      @row-click="openDetail"
    />

    <!-- 详情弹窗 -->
    <el-dialog v-model="detailVisible" :title="detail?.name || '拓扑图详情'" width="600px" top="6vh"
      destroy-on-close>
      <div v-if="detail">
        <el-descriptions :column="2" border size="small">
          <el-descriptions-item label="客户">{{ detail.customer_name }}</el-descriptions-item>
          <el-descriptions-item label="地区">{{ detail.region_name || '-' }}</el-descriptions-item>
          <el-descriptions-item label="来源">
            <el-tag size="small" :type="detail.source === 'draw' ? 'primary' : 'info'">
              {{ detail.source === 'draw' ? '在线绘制' : '文件上传' }}
            </el-tag>
          </el-descriptions-item>
          <el-descriptions-item label="文件数">{{ detail.file_count }}</el-descriptions-item>
        </el-descriptions>
        <p v-if="detail.description" class="detail-text">{{ detail.description }}</p>

        <el-divider content-position="left">关联文件</el-divider>
        <div v-for="f in detail.files" :key="f.id" class="file-item">
          <el-tag size="small" :type="TOPOLOGY_TYPE_TAG[f.file_type] || 'info'" class="file-tag">
            {{ f.file_type }}
          </el-tag>
          <span class="file-name">{{ f.file_path || `#${f.id}（在线图）` }}</span>
          <span v-if="f.upload_by" class="text-muted">上传：{{ f.upload_by }}</span>
          <div class="file-actions">
            <el-button v-if="f.url" size="small" type="primary" link :href="f.url" target="_blank">
              打开
            </el-button>
            <el-button v-if="f.pdf" size="small" type="primary" link :href="f.pdf" target="_blank">
              PDF
            </el-button>
            <el-button v-if="f.vsdx" size="small" type="primary" link :href="f.vsdx" target="_blank">
              VSDX
            </el-button>
            <el-button v-if="f.svg" size="small" type="primary" link :href="f.svg" target="_blank">
              SVG
            </el-button>
          </div>
        </div>
        <el-empty v-if="!detail.files.length" description="暂无文件" :image-size="50" />

        <el-divider content-position="left">在线编辑</el-divider>
        <el-alert v-if="!detail.has_editor" type="info" :closable="false"
          title="该拓扑图为上传文件，不支持在线编辑；可在原 SSR 页面通过「导入后编辑」新建在线图。" />
        <el-button v-else type="primary" :icon="EditPen" @click="openEditor">
          打开编辑器
        </el-button>
      </div>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed } from 'vue'
import { Search, EditPen } from '@element-plus/icons-vue'
import DataTable, { type DataColumn } from '@/components/DataTable.vue'
import {
  fetchTopologies, fetchTopology, TOPOLOGY_TYPE_TAG,
  type TopologyDetail,
} from '@/api/topology'

const query = reactive<Record<string, unknown>>({ search: '' })
const tableRef = ref()

const columns = computed<DataColumn[]>(() => [
  { key: 'name', label: '名称', minWidth: 180, asTitle: true },
  { key: 'customer_name', label: '客户', minWidth: 120 },
  { key: 'type', label: '类型', width: 90, type: 'tag', asTag: true,
    tagMap: TOPOLOGY_TYPE_TAG },
  { key: 'file_count', label: '文件数', width: 80, align: 'center' },
  { key: 'source', label: '来源', width: 90,
    cellClass: (r) => (r.source === 'draw' ? 'source-draw' : '') },
  { key: 'updated_at', label: '更新时间', width: 140 },
  { key: 'actions', label: '操作', width: 90, type: 'action', fixed: 'right',
    actions: [
      { label: '详情', type: 'primary', link: true, perm: 'topology:view', icon: 'View',
        onClick: (row) => openDetail(row) },
    ] },
])

const detailVisible = ref(false)
const detail = ref<TopologyDetail | null>(null)

async function openDetail(row: Record<string, unknown>) {
  try {
    detail.value = await fetchTopology(row.id as number)
    detailVisible.value = true
  } catch { /* toast */ }
}

function openEditor() {
  if (!detail.value) return
  window.location.href = `/topologies/${detail.value.editor_id}/editor`
}

function reload() { tableRef.value?.refresh() }
</script>

<style scoped>
.filter-card { margin-bottom: 12px; }
.filter-row { display: flex; gap: 8px; flex-wrap: wrap; align-items: center; }
.filter-search { width: 240px; max-width: 100%; }
.detail-text { white-space: pre-wrap; word-break: break-all; font-size: 13px;
  margin: 10px 0 0; }
.text-muted { color: var(--itsm-text-muted); font-size: 12px; }
.source-draw { color: var(--el-color-primary); font-weight: 500; }
.file-item { display: flex; align-items: center; gap: 8px; flex-wrap: wrap;
  padding: 8px 10px; border: 1px solid var(--itsm-border); border-radius: 8px; margin-bottom: 8px; }
.file-tag { flex-shrink: 0; text-transform: uppercase; }
.file-name { font-family: var(--font-mono, monospace); font-size: 12px;
  word-break: break-all; min-width: 0; }
.file-actions { display: flex; gap: 4px; margin-left: auto; }
</style>
