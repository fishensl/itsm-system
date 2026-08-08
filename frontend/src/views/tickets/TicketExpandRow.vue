<template>
  <div v-loading="loading" class="expand-detail">
    <template v-if="detail">
      <el-descriptions :column="cols" border size="small">
        <el-descriptions-item label="状态">
          <el-tag size="small" :type="TICKET_STATUS_TAG[detail.status] || 'info'">{{ detail.status }}</el-tag>
        </el-descriptions-item>
        <el-descriptions-item label="优先级">
          <el-tag size="small" :type="detail.priority === '紧急' ? 'danger' : 'warning'">{{ detail.priority }}</el-tag>
        </el-descriptions-item>
        <el-descriptions-item label="客户">{{ detail.customer_name || '-' }}</el-descriptions-item>
        <el-descriptions-item label="关联设备">
          <router-link v-if="detail.related_device_id" :to="`/devices/${detail.related_device_id}`"
            class="row-link">{{ detail.related_device_name || '#' }}</router-link>
          <span v-else>-</span>
        </el-descriptions-item>
        <el-descriptions-item label="处理人">{{ detail.assigned_to || '-' }}</el-descriptions-item>
        <el-descriptions-item label="创建人">{{ detail.created_by || '-' }}</el-descriptions-item>
        <el-descriptions-item label="创建时间">{{ detail.created_at }}</el-descriptions-item>
        <el-descriptions-item label="来源">{{ detail.source_type || '-' }}</el-descriptions-item>
        <el-descriptions-item label="严重级别">{{ detail.severity_level || '-' }}</el-descriptions-item>
        <el-descriptions-item label="处理报告">
          <el-link v-if="detail.report_file" type="primary" :underline="false" @click="downloadLatest">
            {{ detail.report_name || '下载' }}
          </el-link>
          <span v-else class="text-muted">无</span>
        </el-descriptions-item>
        <el-descriptions-item label="资料完整">
          <el-tag size="small" :type="detail.complete ? 'success' : 'warning'">
            {{ detail.complete ? '完整' : '缺:' + (detail.missing_fields || []).join('、') }}
          </el-tag>
        </el-descriptions-item>
      </el-descriptions>

      <el-divider content-position="left">描述</el-divider>
      <p class="detail-text">{{ detail.description || '-' }}</p>

      <template v-if="detail.diagnosis || detail.solution">
        <el-divider content-position="left">处理方案</el-divider>
        <p class="detail-text"><b>诊断：</b>{{ detail.diagnosis || '-' }}</p>
        <p class="detail-text"><b>方案：</b>{{ detail.solution || '-' }}</p>
      </template>

      <!-- 审核意见（退回原因醒目展示） -->
      <template v-if="detail.audit_comment">
        <el-divider content-position="left">审核意见</el-divider>
        <p class="detail-text review-comment">{{ detail.audit_comment }}</p>
        <p class="review-meta">
          审核人：{{ detail.audit_by || '-' }} · {{ detail.audit_at || '-' }}
          <el-tag size="small" :type="detail.audit_status === '通过' ? 'success' : 'danger'" class="audit-tag">
            {{ detail.audit_status }}
          </el-tag>
        </p>
      </template>

      <!-- 提交审核记录时间线 -->
      <el-divider content-position="left">提交审核记录（每次提交 + 每轮审核）</el-divider>
      <VersionTimeline :versions="versions" entity-type="ticket" />

      <!-- 状态机操作 -->
      <el-divider content-position="left">操作</el-divider>
      <div class="action-bar">
        <template v-if="detail.status === TICKET_STATUS.PENDING_ASSIGN">
          <el-input v-model="assignee" placeholder="处理人姓名" class="assign-input" size="small" />
          <el-button v-if="user.hasPerm('ticket:edit')" size="small" type="primary"
            @click="emit('action', 'assign', assignee)">派单</el-button>
          <el-button v-if="user.hasPerm('ticket:edit')" size="small" type="warning"
            @click="emit('action', 'close')">关闭</el-button>
        </template>
        <template v-else-if="detail.status === TICKET_STATUS.ASSIGNED || detail.status === TICKET_STATUS.ACCEPTED">
          <el-button v-if="user.hasPerm('ticket:edit')" size="small" type="success"
            @click="emit('action', 'accept')">接单（开始处理）</el-button>
          <el-button v-if="user.hasPerm('ticket:edit')" size="small" type="info" plain
            @click="emit('action', 'reassign')">撤回重派</el-button>
        </template>
        <template v-else-if="detail.status === TICKET_STATUS.PROCESSING">
          <el-button v-if="user.hasPerm('ticket:edit')" size="small" type="primary"
            @click="emit('submit')">提交审核</el-button>
        </template>
        <template v-else-if="detail.status === TICKET_STATUS.SUBMITTED">
          <el-button v-if="user.hasPerm('ticket:review')" size="small" type="success"
            @click="emit('audit', true)">审核通过</el-button>
          <el-button v-if="user.hasPerm('ticket:review')" size="small" type="danger"
            @click="emit('audit', false)">退回修改</el-button>
        </template>
        <template v-else-if="detail.status === TICKET_STATUS.CHECKED">
          <el-button v-if="user.hasPerm('ticket:edit')" size="small" type="success"
            @click="emit('action', 'accept_check', undefined, true)">验收通过（关闭）</el-button>
          <el-button v-if="user.hasPerm('ticket:edit')" size="small" type="warning"
            @click="emit('action', 'accept_check', undefined, false)">退回处理</el-button>
        </template>
        <el-button v-if="user.hasPerm('ticket:edit') && detail.status !== TICKET_STATUS.CLOSED" size="small" type="info"
          plain @click="emit('action', 'close')">关闭工单</el-button>
        <el-button v-if="user.hasPerm('ticket:edit')" size="small" type="primary" plain
          @click="emit('edit')">编辑</el-button>
        <el-button
          v-if="user.hasPerm('kb:add') && ([TICKET_STATUS.CLOSED, TICKET_STATUS.CHECKED] as string[]).includes(detail.status)"
          size="small" type="success" plain @click="emit('archive')">归档为知识库案例</el-button>
        <el-button v-if="user.hasPerm('ticket:delete')" size="small" type="danger" plain
          @click="emit('delete')">删除</el-button>
      </div>

      <!-- 日志时间轴 -->
      <el-divider content-position="left">操作日志</el-divider>
      <el-timeline v-if="detail.logs?.length">
        <el-timeline-item v-for="(log, i) in detail.logs" :key="i" :timestamp="log.created_at" placement="top"
          size="small">
          <div class="log-item">
            <b>{{ log.action }}</b>
            <span class="log-op">{{ log.operator }}</span>
            <div v-if="log.comment" class="log-comment">{{ log.comment }}</div>
          </div>
        </el-timeline-item>
      </el-timeline>
      <el-empty v-else description="暂无日志" :image-size="50" />
    </template>
  </div>
</template>

<script setup lang="ts">
import { ref, watch, computed } from 'vue'
import { useMobile } from '@/utils/useMobile'
import VersionTimeline from '@/components/VersionTimeline.vue'
import { useUserStore } from '@/stores/user'
import { fetchTicket, fetchTicketVersions, versionReportUrl, TICKET_STATUS_TAG, type Ticket } from '@/api/tickets'
import { TICKET_STATUS } from '@/utils/status'

const { isMobile } = useMobile()
// 移动端降为 2 列
const cols = computed(() => (isMobile.value ? 2 : 3))
import type { SubmissionVersion as SV } from '@/api/inspections'

const props = defineProps<{ row: Record<string, unknown> }>()
const emit = defineEmits<{
  (e: 'action', action: string, assignee?: string, approved?: boolean): void
  (e: 'audit', approved: boolean): void
  (e: 'submit'): void
  (e: 'edit'): void
  (e: 'archive'): void
  (e: 'delete'): void
}>()

const user = useUserStore()
const loading = ref(false)
const detail = ref<Ticket | null>(null)
const versions = ref<SV[]>([])
const assignee = ref('')

async function load() {
  loading.value = true
  try {
    const [full, vers] = await Promise.all([
      fetchTicket(props.row.id as number),
      fetchTicketVersions(props.row.id as number),
    ])
    detail.value = full
    versions.value = vers
    assignee.value = full.assigned_to || ''
  } catch { /* toast */ } finally {
    loading.value = false
  }
}

function downloadLatest() {
  const latest = versions.value.slice().reverse().find((v) => v.report_file)
  if (!latest) return
  window.open(versionReportUrl('ticket', latest.id), '_blank')
}

// 列表刷新后行对象被替换 → 自动重取详情保持新鲜
watch(() => props.row, () => { load() })

load()
</script>

<style scoped>
.expand-detail { padding: 4px 8px 8px; }
.detail-text { white-space: pre-wrap; word-break: break-all; font-size: 13px; margin: 0; }
.review-comment { color: var(--el-color-danger); font-weight: 600; white-space: pre-wrap; }
.review-meta { font-size: 12px; color: var(--itsm-text-muted); display: flex; align-items: center; gap: 6px; }
.audit-tag { margin-left: 4px; }
.action-bar { display: flex; gap: 8px; flex-wrap: wrap; align-items: center; }
.assign-input { width: 160px; }
.log-item { font-size: 13px; }
.log-op { color: var(--itsm-text-muted); margin-left: 8px; font-size: 12px; }
.log-comment { color: var(--itsm-text-muted); font-size: 12px; margin-top: 2px; }
.text-muted { color: var(--itsm-text-muted); }
.row-link { color: var(--el-color-primary); text-decoration: none; font-weight: 500; }
</style>
