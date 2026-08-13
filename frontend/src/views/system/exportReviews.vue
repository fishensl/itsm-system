<template>
  <div class="page-container">
    <div class="page-header">
      <h2 class="page-title">导出审核</h2>
      <div class="header-actions">
        <el-button :icon="Refresh" plain @click="load">刷新</el-button>
      </div>
    </div>

    <el-card shadow="never">
      <template #header>
        <span class="card-title">待审核申请（设备密码导出）</span>
      </template>
      <DataTable
        ref="tableRef"
        :columns="columns"
        :fetch-data="fetchPage"
        row-key="id"
        empty-text="暂无待审核申请"
        :column-settings="{ storageKey: 'cols_export_reviews' }"
      />
    </el-card>

    <!-- 审核弹窗 -->
    <el-dialog v-model="reviewVisible" :title="reviewAction === 'approve' ? '通过申请' : '驳回申请'"
      width="480px" destroy-on-close>
      <el-form label-width="80px">
        <el-form-item :label="label('realname', '申请人')">
          {{ reviewTarget?.realname || reviewTarget?.username }}
        </el-form-item>
        <el-form-item :label="label('reason', '申请原因')">
          <div class="reason-box">{{ reviewTarget?.reason }}</div>
        </el-form-item>
        <el-form-item :label="reviewAction === 'approve' ? label('review_comment', '审核意见') : '驳回原因'">
          <el-input v-model="comment" type="textarea" :rows="3"
            :placeholder="reviewAction === 'reject' ? '驳回原因必填' : '可选备注'" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="reviewVisible = false">取消</el-button>
        <el-button :type="reviewAction === 'approve' ? 'success' : 'danger'" :loading="submitting"
          @click="doReview">
          {{ reviewAction === 'approve' ? '通过并生成加密包' : '确认驳回' }}
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import { Refresh } from '@element-plus/icons-vue'
import { useUiStore } from '@/stores/ui'
import { fetchExportReviews, reviewExportRequest, type ExportReviewItem } from '@/api/system'
import { entityFieldLabel, fetchEntityMeta, type EntityMeta } from '@/api/meta'
import DataTable, { type DataColumn } from '@/components/DataTable.vue'

const ui = useUiStore()
const tableRef = ref()
const metadata = ref<EntityMeta>()
const reviewVisible = ref(false)
const reviewAction = ref<'approve' | 'reject'>('approve')
const reviewTarget = ref<ExportReviewItem | null>(null)
const comment = ref('')
const submitting = ref(false)

function label(key: string, fallback: string) {
  return entityFieldLabel(metadata.value, key, fallback, 'detail')
}

const columns = computed<DataColumn[]>(() => [
  { key: 'created_at', label: label('created_at', '申请时间'), width: 150 },
  { key: 'realname', label: label('realname', '申请人'), width: 140, asTitle: true,
    render: (row) => String(row.realname || row.username || '-') },
  { key: 'reason', label: label('reason', '申请原因'), minWidth: 240 },
  { key: 'actions', label: '操作', width: 180, type: 'action', fixed: 'right', actions: [
    { label: '通过', type: 'success', link: true,
      onClick: (row) => openReview(row as unknown as ExportReviewItem, 'approve') },
    { label: '驳回', type: 'danger', link: true,
      onClick: (row) => openReview(row as unknown as ExportReviewItem, 'reject') },
  ] },
])

async function fetchPage(params: Record<string, unknown>) {
  const data = await fetchExportReviews()
  const page = Number(params.page) || 1
  const page_size = Number(params.page_size) || 20
  const start = (page - 1) * page_size
  return { items: data.items.slice(start, start + page_size), total: data.items.length,
    page, page_size }
}

function load() {
  tableRef.value?.refresh()
}

function openReview(row: ExportReviewItem, action: 'approve' | 'reject') {
  reviewTarget.value = row
  reviewAction.value = action
  comment.value = ''
  reviewVisible.value = true
}

async function doReview() {
  if (!reviewTarget.value) return
  if (reviewAction.value === 'reject' && !comment.value.trim()) {
    ui.toast('驳回原因必填', 'warning')
    return
  }
  submitting.value = true
  try {
    await reviewExportRequest(reviewTarget.value.id, reviewAction.value, comment.value.trim())
    ui.toast(reviewAction.value === 'approve' ? '已通过，加密包已生成' : '已驳回', 'success')
    reviewVisible.value = false
    load()
  } catch (e) {
    ui.toast((e as Error).message, 'error')
  } finally {
    submitting.value = false
  }
}

onMounted(() => {
  fetchEntityMeta('device_export_review')
    .then((result) => { metadata.value = result })
    .catch(() => { /* 兼容滚动发布期间的旧后端 */ })
})
</script>

<style scoped>
.card-title { font-weight: 600; font-size: 14px; }
.reason-box {
  width: 100%; padding: 8px 10px; border-radius: 6px;
  background: var(--el-fill-color-light); font-size: 13px; white-space: pre-wrap;
}
</style>
