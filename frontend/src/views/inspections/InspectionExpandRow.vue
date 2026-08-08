<template>
  <div v-loading="loading" class="expand-detail">
    <template v-if="detail">
      <el-descriptions :column="cols" border size="small">
        <el-descriptions-item label="总体状态">
          <el-tag size="small" :type="OVERALL_STATUS_TAG[detail.overall_status] || 'info'">
            {{ detail.overall_status }}
          </el-tag>
        </el-descriptions-item>
        <el-descriptions-item label="审核状态">
          <el-tag size="small" :type="REVIEW_STATUS_TAG[detail.review_status] || 'info'">
            {{ detail.review_status }}
          </el-tag>
        </el-descriptions-item>
        <el-descriptions-item label="客户">{{ detail.customer_name || '-' }}</el-descriptions-item>
        <el-descriptions-item label="关联任务">{{ detail.task_title || '-' }}</el-descriptions-item>
        <el-descriptions-item label="巡检日期">{{ detail.inspection_date || '-' }}</el-descriptions-item>
        <el-descriptions-item label="巡检人员">{{ detail.inspector_name || '-' }}</el-descriptions-item>
        <el-descriptions-item label="现场报告">
          <el-link v-if="detail.submitted_report_name" type="primary" :underline="false"
            @click="downloadLatest">下载</el-link>
          <span v-else class="text-muted">无</span>
        </el-descriptions-item>
        <el-descriptions-item label="正式报告">
          <el-link v-if="detail.report_file && detail.report_file_name" type="primary" :underline="false"
            @click="downloadFormal">下载</el-link>
          <span v-else class="text-muted">未生成</span>
        </el-descriptions-item>
        <el-descriptions-item label="资料完整">
          <el-tag size="small" :type="detail.complete ? 'success' : 'warning'">
            {{ detail.complete ? '完整' : '缺:' + (detail.missing_fields || []).join('、') }}
          </el-tag>
        </el-descriptions-item>
        <el-descriptions-item label="巡检地点">{{ detail.location || '-' }}</el-descriptions-item>
        <el-descriptions-item label="创建时间">{{ detail.created_at }}</el-descriptions-item>
      </el-descriptions>

      <el-divider content-position="left">结论</el-divider>
      <p class="detail-text">{{ detail.conclusion || '-' }}</p>

      <template v-if="detail.review_comment">
        <el-divider content-position="left">审核意见</el-divider>
        <p class="detail-text review-comment">{{ detail.review_comment }}</p>
      </template>

      <el-divider content-position="left">提交审核记录（每次上传 + 每轮审核）</el-divider>
      <VersionTimeline :versions="versions" entity-type="inspection" />

      <el-divider content-position="left">操作</el-divider>
      <div class="action-bar">
        <template v-if="detail.review_status === '草稿'">
          <el-button v-if="user.hasPerm('inspection:edit')" size="small" type="primary"
            @click="emit('submit')">提交审核</el-button>
        </template>
        <template v-else-if="detail.review_status === '待审核'">
          <el-button v-if="user.hasPerm('inspection:review')" size="small" type="success"
            @click="emit('review', true)">审核通过</el-button>
          <el-button v-if="user.hasPerm('inspection:review')" size="small" type="danger"
            @click="emit('review', false)">退回修改</el-button>
        </template>
        <el-button v-if="user.hasPerm('inspection:edit')" size="small" type="primary" plain
          @click="emit('edit')">编辑</el-button>
        <el-button v-if="user.hasPerm('inspection:delete')" size="small" type="danger" plain
          @click="emit('delete')">删除</el-button>
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import { ref, watch, computed } from 'vue'
import { useMobile } from '@/utils/useMobile'
import VersionTimeline from '@/components/VersionTimeline.vue'
import { useUserStore } from '@/stores/user'
import {
  fetchInspection, fetchInspectionVersions,
  versionReportUrl, formalReportUrl,
  OVERALL_STATUS_TAG, REVIEW_STATUS_TAG, type Inspection, type SubmissionVersion,
} from '@/api/inspections'

const { isMobile } = useMobile()
// 移动端降为 2 列，避免每项过窄
const cols = computed(() => (isMobile.value ? 2 : 2))

const props = defineProps<{ row: Record<string, unknown> }>()
const emit = defineEmits<{
  (e: 'submit'): void
  (e: 'review', approved: boolean): void
  (e: 'edit'): void
  (e: 'delete'): void
}>()

const user = useUserStore()
const loading = ref(false)
const detail = ref<Inspection | null>(null)
const versions = ref<SubmissionVersion[]>([])

async function load() {
  loading.value = true
  try {
    const [full, vers] = await Promise.all([
      fetchInspection(props.row.id as number),
      fetchInspectionVersions(props.row.id as number),
    ])
    detail.value = full
    versions.value = vers
  } catch { /* toast */ } finally {
    loading.value = false
  }
}

function downloadLatest() {
  const latest = versions.value.slice().reverse().find((v) => v.report_file)
  if (!latest || !detail.value) return
  window.open(versionReportUrl('inspection', latest.id), '_blank')
}

function downloadFormal() {
  if (!detail.value?.report_file_name) return
  window.open(formalReportUrl(detail.value.report_file_name), '_blank')
}

// 列表刷新后行对象被替换 → 自动重取详情保持新鲜
watch(() => props.row, () => { load() })

load()
</script>

<style scoped>
.expand-detail { padding: 4px 8px 8px; }
.detail-text { white-space: pre-wrap; word-break: break-all; font-size: 13px; margin: 0; }
.review-comment { color: var(--el-color-danger); font-weight: 600; }
.action-bar { display: flex; gap: 8px; flex-wrap: wrap; align-items: center; }
.text-muted { color: var(--itsm-text-muted); }
</style>
