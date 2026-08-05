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
        <div class="vt-card" :class="{ rejected: v.review_status === '已退回', approved: v.review_status === '已通过' }">
          <!-- 提交阶段 -->
          <div class="vt-head">
            <span class="vt-no">第 {{ v.version_no }} 轮提交</span>
            <el-tag v-if="v.review_status" size="small" :type="REVIEW_TAG[v.review_status] || 'info'">
              {{ v.review_status }}
            </el-tag>
            <el-tag v-else size="small" type="info">待审核</el-tag>
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
            <template v-if="v.content?.remark">
              <div class="vt-row"><span class="vt-label">提交备注</span><span class="vt-remark">{{ v.content.remark }}</span></div>
            </template>
            <div v-if="v.report_file" class="vt-row">
              <span class="vt-label">报告</span>
              <el-link type="primary" :underline="false" @click="download(v)">
                <el-icon style="margin-right: 2px"><Download /></el-icon>{{ v.report_name || '下载报告' }}
              </el-link>
            </div>
            <div v-else class="vt-row"><span class="vt-label">报告</span><span class="vt-none">未上传</span></div>

            <!-- 提交资料明细（配置备份/拓扑图/资产清单） -->
            <div v-if="v.assets?.length" class="vt-assets">
              <div v-for="a in v.assets" :key="a.id" class="vt-row">
                <span class="vt-label">{{ ASSET_LABELS[a.asset_type] || a.asset_type }}</span>
                <template v-if="a.skip_reason">
                  <span class="vt-skip">未上传（原因：{{ a.skip_reason }}）</span>
                </template>
                <template v-else>
                  <template v-if="a.asset_type === 'config_text' && a.has_content">
                    <el-link type="primary" :underline="false" @click="viewContent(a)">
                      <el-icon style="margin-right: 2px"><View /></el-icon>{{ a.device_name || '配置' }} 在线查看
                    </el-link>
                  </template>
                  <template v-else-if="a.asset_type === 'topology' && a.target_id">
                    <el-link type="primary" :underline="false" @click="openTopology()">
                      <el-icon style="margin-right: 2px"><Share /></el-icon>{{ a.file_name || '拓扑图' }}（已同步）
                    </el-link>
                  </template>
                  <template v-else>
                    <el-link v-if="a.file_name" type="primary" :underline="false" @click="downloadAsset(a)">
                      <el-icon style="margin-right: 2px"><Download /></el-icon>{{ a.file_name }}
                    </el-link>
                    <span v-else class="vt-none">（无附件）</span>
                  </template>
                  <span v-if="a.device_name" class="vt-device">· {{ a.device_name }}</span>
                </template>
              </div>
            </div>
          </div>

          <!-- 审核阶段 -->
          <div v-if="v.review_status" class="vt-review">
            <div class="vt-review-head">
              <span class="vt-reviewer">审核人：{{ v.reviewed_by_name || '-' }} · {{ v.reviewed_at || '-' }}</span>
            </div>
            <template v-if="v.review_status === '已退回'">
              <div v-if="v.revision_requirements" class="vt-requirements">
                <span class="vt-req-label">需要修改：</span>{{ v.revision_requirements }}
              </div>
              <div v-if="v.review_comment" class="vt-comment">退回原因：{{ v.review_comment }}</div>
            </template>
            <template v-else>
              <div v-if="v.review_comment" class="vt-comment">审核意见：{{ v.review_comment }}</div>
            </template>
          </div>
        </div>
      </el-timeline-item>
    </el-timeline>
  </div>
</template>

<script setup lang="ts">
import { Download, View, Share } from '@element-plus/icons-vue'
import { ElMessageBox } from 'element-plus'
import type { SubmissionVersion, SubmissionAsset } from '@/api/inspections'
import { versionReportUrl, submissionAssetUrl, fetchSubmissionAssetContent } from '@/api/inspections'

const props = defineProps<{
  versions: SubmissionVersion[]
  entityType: 'inspection' | 'ticket'
}>()

const ASSET_LABELS: Record<string, string> = {
  report: '巡检报告',
  config_zip: '完整配置包',
  config_text: '设备文本配置',
  topology: '拓扑图',
  asset_list: '资产清单',
}

function viewContent(a: SubmissionAsset) {
  fetchSubmissionAssetContent(a.id)
    .then((r) => {
      ElMessageBox.alert(r.content || '（空）', `配置文本 · ${a.device_name || a.file_name}`, {
        customStyle: { maxHeight: '70vh', overflow: 'auto' },
        confirmButtonText: '关闭',
      }).catch(() => {})
    })
    .catch(() => { /* toast */ })
}

function downloadAsset(a: SubmissionAsset) {
  window.open(submissionAssetUrl(a.id), '_blank')
}

function openTopology() {
  window.open(`/app/topologies`, '_blank')
}

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
.vt-card.approved { border-color: var(--el-color-success-light-5); }
.vt-head { display: flex; align-items: center; gap: 8px; margin-bottom: 6px; }
.vt-no { font-weight: 600; font-size: 13px; }
.vt-content { font-size: 12px; color: var(--el-text-color-regular); }
.vt-row { display: flex; gap: 6px; margin: 2px 0; }
.vt-label { color: var(--el-text-color-secondary); flex-shrink: 0; min-width: 60px; }
.vt-remark { white-space: pre-wrap; color: var(--el-text-color-regular); }
.vt-none { color: var(--el-text-color-placeholder); }
.vt-assets { margin-top: 4px; padding: 4px 6px; border-radius: 4px; background: var(--el-fill-color-light); }
.vt-skip { color: var(--el-color-warning); font-size: 12px; }
.vt-device { color: var(--el-text-color-secondary); font-size: 12px; }
.vt-review { margin-top: 6px; padding-top: 6px; border-top: 1px dashed var(--el-border-color-lighter); font-size: 12px; }
.vt-review-head { margin-bottom: 2px; }
.vt-reviewer { color: var(--el-text-color-secondary); }
.vt-requirements {
  color: var(--el-color-danger);
  font-weight: 600;
  white-space: pre-wrap;
  margin: 2px 0;
  padding: 4px 6px;
  background: var(--el-color-danger-light-9);
  border-radius: 4px;
}
.vt-req-label { color: var(--el-color-danger); }
.vt-comment { color: var(--el-text-color-primary); white-space: pre-wrap; margin: 2px 0; }
</style>
