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
      <el-table v-if="items.length" :data="items" size="small" border>
        <el-table-column prop="created_at" label="申请时间" width="150" />
        <el-table-column label="申请人" width="140">
          <template #default="{ row }">{{ row.realname || row.username }}</template>
        </el-table-column>
        <el-table-column prop="reason" label="申请原因" min-width="240" show-overflow-tooltip />
        <el-table-column label="操作" width="220">
          <template #default="{ row }">
            <el-button size="small" type="success" link @click="openReview(row, 'approve')">通过</el-button>
            <el-button size="small" type="danger" link @click="openReview(row, 'reject')">驳回</el-button>
          </template>
        </el-table-column>
      </el-table>
      <el-empty v-else description="暂无待审核申请" :image-size="60" />
    </el-card>

    <!-- 审核弹窗 -->
    <el-dialog v-model="reviewVisible" :title="reviewAction === 'approve' ? '通过申请' : '驳回申请'"
      width="480px" destroy-on-close>
      <el-form label-width="80px">
        <el-form-item label="申请人">
          {{ reviewTarget?.realname || reviewTarget?.username }}
        </el-form-item>
        <el-form-item label="申请原因">
          <div class="reason-box">{{ reviewTarget?.reason }}</div>
        </el-form-item>
        <el-form-item :label="reviewAction === 'approve' ? '备注' : '驳回原因'">
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
import { ref, onMounted } from 'vue'
import { Refresh } from '@element-plus/icons-vue'
import { useUiStore } from '@/stores/ui'
import { fetchExportReviews, reviewExportRequest, type ExportReviewItem } from '@/api/system'

const ui = useUiStore()
const items = ref<ExportReviewItem[]>([])
const reviewVisible = ref(false)
const reviewAction = ref<'approve' | 'reject'>('approve')
const reviewTarget = ref<ExportReviewItem | null>(null)
const comment = ref('')
const submitting = ref(false)

async function load() {
  try {
    const d = await fetchExportReviews()
    items.value = d.items
  } catch (e) {
    ui.toast((e as Error).message, 'error')
  }
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

onMounted(load)
</script>

<style scoped>
.card-title { font-weight: 600; font-size: 14px; }
.reason-box {
  width: 100%; padding: 8px 10px; border-radius: 6px;
  background: var(--el-fill-color-light); font-size: 13px; white-space: pre-wrap;
}
</style>
