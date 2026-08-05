<template>
  <div class="version-timeline">
    <el-empty v-if="!versions.length" description="暂无提交记录" :image-size="50" />
    <el-timeline v-else>
      <el-timeline-item
        v-for="v in versions"
        :key="v.id"
        :type="timelineType(v)"
        :hollow="v.review_status === ''"
        :timestamp="`${v.submitted_at} · ${v.submitted_by_name || '-'}`"
        placement="top"
      >
        <div class="vt-card" :class="{ rejected: v.review_status === '已退回' }">
          <div class="vt-head">
            <span class="vt-no">第 {{ v.version_no }} 次提交</span>
            <el-tag v-if="v.review_status" size="small" :type="REVIEW_TAG[v.review_status] || 'info'">
              {{ v.review_status }}
            </el-tag>
            <el-tag v-else size="small" type="info">未审核</el-tag>
          </div>
          <div class="vt-content">
            <template v-if="v.content?.conclusion">
              <div class="vt-row"><span class="vt-label">结论</span>{{ v.content.conclusion }}</div>
            </template>
            <template v-if="v.content?.diagnosis">
              <div class="vt-row"><span class="vt-label">诊断</span>{{ v.content.diagnosis }}</div>
            </template>
            <template v-if="v.content?.solution">
              <div class="vt-row"><span class="vt-label">方案</span>{{ v.content.solution }}</div>
            </template>
            <div v-if="v.report_file" class="vt-row">
              <span class="vt-label">报告</span>
              <el-link type="primary" :underline="false" @click="download(v)">
                <el-icon style="margin-right: 2px"><Download /></el-icon>{{ v.report_name || '下载报告' }}
              </el-link>
            </div>
            <div v-else class="vt-row"><span class="vt-label">报告</span><span class="vt-none">未上传</span></div>
          </div>
          <div v-if="v.review_status" class="vt-review">
            <template v-if="v.review_status === '已退回'">
              <div class="vt-reject">退回原因：{{ v.review_comment || '（未填写）' }}</div>
              <div class="vt-reviewer">审核人：{{ v.reviewed_by_name || '-' }} · {{ v.reviewed_at || '-' }}</div>
            </template>
            <template v-else>
              <div v-if="v.review_comment" class="vt-comment">审核意见：{{ v.review_comment }}</div>
              <div v-if="v.reviewed_by_name" class="vt-reviewer">审核人：{{ v.reviewed_by_name }} · {{ v.reviewed_at || '-' }}</div>
            </template>
          </div>
        </div>
      </el-timeline-item>
    </el-timeline>
  </div>
</template>

<script setup lang="ts">
import { Download } from '@element-plus/icons-vue'
import type { SubmissionVersion } from '@/api/inspections'
import { versionReportUrl } from '@/api/inspections'

const props = defineProps<{
  versions: SubmissionVersion[]
  entityType: 'inspection' | 'ticket'
}>()

const REVIEW_TAG: Record<string, 'primary' | 'success' | 'warning' | 'danger' | 'info'> = {
  待审核: 'warning',
  已通过: 'success',
  已退回: 'danger',
}

function timelineType(v: SubmissionVersion): 'primary' | 'success' | 'warning' | 'danger' {
  if (v.review_status === '已通过') return 'success'
  if (v.review_status === '已退回') return 'danger'
  if (v.review_status === '待审核') return 'warning'
  return 'primary'
}

function download(v: SubmissionVersion) {
  window.open(versionReportUrl(props.entityType, v.id), '_blank')
}
</script>

<style scoped>
.version-timeline { padding: 4px 0; }
.vt-card {
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 6px;
  padding: 8px 10px;
  background: var(--el-fill-color-blank);
}
.vt-card.rejected { border-color: var(--el-color-danger-light-5); background: var(--el-color-danger-light-9); }
.vt-head { display: flex; align-items: center; gap: 8px; margin-bottom: 6px; }
.vt-no { font-weight: 600; font-size: 13px; }
.vt-content { font-size: 12px; color: var(--el-text-color-regular); }
.vt-row { display: flex; gap: 6px; margin: 2px 0; }
.vt-label { color: var(--el-text-color-secondary); flex-shrink: 0; min-width: 36px; }
.vt-none { color: var(--el-text-color-placeholder); }
.vt-review { margin-top: 6px; padding-top: 6px; border-top: 1px dashed var(--el-border-color-lighter); font-size: 12px; }
.vt-reject { color: var(--el-color-danger); font-weight: 600; white-space: pre-wrap; }
.vt-comment { color: var(--el-text-color-primary); white-space: pre-wrap; }
.vt-reviewer { color: var(--el-text-color-secondary); margin-top: 2px; }
</style>
