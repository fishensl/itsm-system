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
        <el-descriptions-item label="客户">
          <template v-if="detail.customer">
            <span>{{ detail.customer.name || '-' }}</span>
            <span v-if="detail.customer.office_room || detail.customer.office" class="cust-min">
              （{{ [detail.customer.office, detail.customer.office_room].filter(Boolean).join('·') }}）
            </span>
            <span v-if="detail.customer.map_location" class="cust-min">{{ detail.customer.map_location }}</span>
          </template>
          <span v-else>{{ detail.customer_name || '-' }}</span>
        </el-descriptions-item>
        <el-descriptions-item label="关联设备">
          <router-link v-if="detail.related_device_id" :to="`/devices/${detail.related_device_id}`"
            class="row-link">{{ detail.related_device_name || '#' }}</router-link>
          <span v-else>-</span>
        </el-descriptions-item>
        <el-descriptions-item label="处理人">{{ detail.assigned_to || '-' }}</el-descriptions-item>
        <el-descriptions-item label="故障分类">{{ detail.fault_category || '-' }}</el-descriptions-item>
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

      <!-- 合同例外审批（过期客户创建的工单） -->
      <template v-if="detail.status === TICKET_STATUS.CONTRACT_REVIEW">
        <el-divider content-position="left">合同例外审批</el-divider>
        <p class="detail-text">
          <el-tag size="small" type="warning" class="mr-2">客户合同已过期</el-tag>
          例外原因：{{ detail.contract_exception_reason || '-' }}
        </p>
        <el-button v-if="canContractReview" size="small" type="success"
          @click="emit('contract-review', true)">审核通过（安排处理）</el-button>
        <el-button v-if="canContractReview" size="small" type="danger"
          @click="emit('contract-review', false)">拒绝（关闭工单）</el-button>
      </template>

      <!-- 处置进展（V28） -->
      <template v-if="detail.progresses?.length">
        <el-divider content-position="left">处置进展</el-divider>
        <div v-for="(p, i) in detail.progresses" :key="i" class="progress-item">
          <div class="progress-head">
            <span class="progress-op">{{ p.operator }}</span>
            <span class="progress-time">{{ p.created_at }}</span>
          </div>
          <div v-if="p.content" class="progress-content">{{ p.content }}</div>
          <div v-if="p.photos?.length" class="progress-photos">
            <el-image v-for="(ph, j) in p.photos" :key="j" :src="photoUrl(ph)" :preview-src-list="p.photos.map(photoUrl)"
              fit="cover" class="progress-photo" :preview-teleported="true" />
          </div>
        </div>
      </template>

      <!-- 挂起历史（V28） -->
      <template v-if="detail.suspends?.length">
        <el-divider content-position="left">挂起记录</el-divider>
        <div v-for="(s, i) in detail.suspends" :key="i" class="suspend-item">
          <span class="suspend-reason">{{ s.reason }}</span>
          <span class="suspend-meta">{{ s.operator }} · {{ s.started_at }} ~ {{ s.ended_at || '挂起中' }}（{{ s.duration }}）</span>
        </div>
      </template>

      <!-- 状态机操作 -->
      <el-divider content-position="left">操作</el-divider>
      <div class="action-bar">
        <template v-if="detail.status === TICKET_STATUS.PENDING_ASSIGN">
          <el-select v-model="assignUserId" filterable placeholder="选择处理人" size="small"
            class="assign-select">
            <el-option v-for="u in assignUsers" :key="u.id" :label="u.name" :value="u.id" />
          </el-select>
          <el-button v-if="canAssign" size="small" type="primary"
            @click="emit('action', 'assign', assignUserName)">派单</el-button>
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
          <el-button v-if="user.hasPerm('ticket:edit')" size="small" type="warning" plain
            @click="emit('suspend')">挂起（等待/暂停）</el-button>
        </template>
        <template v-else-if="detail.status === TICKET_STATUS.SUSPENDED">
          <el-button v-if="user.hasPerm('ticket:edit')" size="small" type="success"
            @click="emit('action', 'resume')">恢复处理</el-button>
          <el-button v-if="user.hasPerm('ticket:edit')" size="small" type="primary"
            @click="emit('submit')">无法处置，提交审核</el-button>
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
        <el-button v-if="canAddProgress" size="small" type="primary" plain
          @click="emit('progress')">添加处置进展</el-button>
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
import { fetchDepartments } from '@/api/system'
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
  (e: 'suspend'): void
  (e: 'progress'): void
  (e: 'contract-review', approved: boolean): void
  (e: 'edit'): void
  (e: 'archive'): void
  (e: 'delete'): void
}>()

const user = useUserStore()
const loading = ref(false)
const detail = ref<Ticket | null>(null)
const versions = ref<SV[]>([])
const assignUserId = ref<number | null>(null)
const assignUsers = ref<{ id: number; name: string }[]>([])
const assignUserName = computed(() =>
  assignUsers.value.find((u) => u.id === assignUserId.value)?.name || '')

/** 派单权限：ticket:assign 或部门主管（admin 短路） */
const canAssign = computed(() =>
  user.hasPerm('ticket:assign') || user.isSupervisor)

/** 合同例外审核权限：contract:review 或 admin 或部门主管 */
const canContractReview = computed(() => {
  if (!detail.value) return false
  if (detail.value.status !== TICKET_STATUS.CONTRACT_REVIEW) return false
  if (user.hasPerm('contract:review')) return true
  return user.hasPerm('ticket:review')  // 审核岗（含 admin/主管授权）可审
})

/** 处置进展可写：处理中/已挂起/待审核状态，工程师/主管/管理员 */
const canAddProgress = computed(() => {
  if (!detail.value) return false
  return ['处理中', '已挂起', '待审核'].includes(detail.value.status) &&
    (user.hasPerm('ticket:edit') || user.hasPerm('ticket:review'))
})

const photoUrl = (path: string) => `/static/${path}`

async function load() {
  loading.value = true
  try {
    const [full, vers] = await Promise.all([
      fetchTicket(props.row.id as number),
      fetchTicketVersions(props.row.id as number),
    ])
    detail.value = full
    versions.value = vers
    assignUserId.value = null
    if (!assignUsers.value.length) {
      const d = await fetchDepartments()
      assignUsers.value = d.users
    }
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
.assign-select { width: 160px; }
.log-item { font-size: 13px; }
.log-op { color: var(--itsm-text-muted); margin-left: 8px; font-size: 12px; }
.log-comment { color: var(--itsm-text-muted); font-size: 12px; margin-top: 2px; }
.text-muted { color: var(--itsm-text-muted); }
.row-link { color: var(--el-color-primary); text-decoration: none; font-weight: 500; }
.cust-min { color: var(--itsm-text-muted); font-size: 12px; margin-left: 6px; }
.progress-item { margin-bottom: 10px; }
.progress-head { display: flex; gap: 8px; align-items: center; font-size: 12px; }
.progress-op { font-weight: 600; color: var(--itsm-primary); }
.progress-time { color: var(--itsm-text-muted); }
.progress-content { white-space: pre-wrap; word-break: break-all; font-size: 13px; margin-top: 4px; }
.progress-photos { display: flex; gap: 6px; flex-wrap: wrap; margin-top: 6px; }
.progress-photo { width: 72px; height: 72px; border-radius: 6px; }
.suspend-item { display: flex; flex-direction: column; gap: 2px; padding: 4px 0; font-size: 12px; }
.suspend-reason { font-weight: 500; font-size: 13px; }
.suspend-meta { color: var(--itsm-text-muted); }
.mr-2 { margin-right: 8px; }
</style>
