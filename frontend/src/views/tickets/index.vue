<template>
  <div class="page-container">
    <div class="page-header">
      <h2 class="page-title">工单管理</h2>
      <div class="header-actions">
        <el-button :icon="Download" plain @click="doExport('excel')">导出记录</el-button>
        <el-button :icon="FolderOpened" plain @click="doExport('zip')">导出报告包</el-button>
        <el-button v-if="user.hasPerm('ticket:add')" type="primary" :icon="Plus" @click="openCreate">
          新建工单
        </el-button>
      </div>
    </div>

    <!-- 筛选 -->
    <el-card shadow="never" class="filter-card">
      <div class="filter-row">
        <el-input v-model="query.search" placeholder="搜索标题 / 单号" clearable class="filter-search"
          @keyup.enter="reload" @clear="reload" />
        <el-select v-model="query.status" placeholder="状态" clearable class="filter-item" @change="reload">
          <el-option v-for="s in dicts?.statuses || []" :key="s" :label="s" :value="s" />
        </el-select>
        <el-select v-model="query.priority" placeholder="优先级" clearable class="filter-item" @change="reload">
          <el-option v-for="p in dicts?.priorities || []" :key="p" :label="p" :value="p" />
        </el-select>
        <el-select v-model="query.customer_id" placeholder="客户" clearable filterable class="filter-item" @change="reload">
          <el-option v-for="c in dicts?.customers || []" :key="c.id" :label="c.name" :value="c.id" />
        </el-select>
        <el-date-picker v-model="dateRange" type="daterange" value-format="YYYY-MM-DD" start-placeholder="开始日期"
          end-placeholder="结束日期" class="filter-item date-range" @change="onDateChange" />
        <el-checkbox v-model="query.scope" true-label="mine" false-label="all" @change="reload">
          只看我的
        </el-checkbox>
        <el-checkbox v-model="incompleteOnly" @change="reload">仅看不完整</el-checkbox>
        <el-button type="primary" plain :icon="Search" @click="reload">查询</el-button>
      </div>
    </el-card>

    <!-- 列表 -->
    <DataTable
      ref="tableRef"
      :columns="columns"
      :fetch-data="fetchTickets"
      :query="query"
      row-key="id"
      @row-click="openDetail"
    />

    <!-- 详情弹窗 -->
    <el-drawer v-model="detailVisible" :title="detail ? `${detail.number} · ${detail.title}` : ''"
      size="620px" destroy-on-close>
      <div v-if="detail">
        <el-descriptions :column="2" border size="small">
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
            <el-button v-if="user.hasPerm('ticket:edit')" size="small" type="primary" @click="doAction('assign')">
              派单
            </el-button>
            <el-button v-if="user.hasPerm('ticket:edit')" size="small" type="warning" @click="doAction('close')">
              关闭
            </el-button>
          </template>
          <template v-else-if="detail.status === TICKET_STATUS.ASSIGNED || detail.status === TICKET_STATUS.ACCEPTED">
            <el-button v-if="user.hasPerm('ticket:edit')" size="small" type="success" @click="doAction('accept')">
              接单（开始处理）
            </el-button>
            <el-button v-if="user.hasPerm('ticket:edit')" size="small" type="info" plain @click="doAction('reassign')">
              撤回重派
            </el-button>
          </template>
          <template v-else-if="detail.status === TICKET_STATUS.PROCESSING">
            <el-button v-if="user.hasPerm('ticket:edit')" size="small" type="primary" @click="openSubmit">
              提交审核
            </el-button>
          </template>
          <template v-else-if="detail.status === TICKET_STATUS.SUBMITTED">
            <el-button v-if="user.hasPerm('ticket:review')" size="small" type="success" @click="openAudit(true)">
              审核通过
            </el-button>
            <el-button v-if="user.hasPerm('ticket:review')" size="small" type="danger" @click="openAudit(false)">
              退回修改
            </el-button>
          </template>
          <template v-else-if="detail.status === TICKET_STATUS.CHECKED">
            <el-button v-if="user.hasPerm('ticket:edit')" size="small" type="success" @click="doAction('accept_check', true)">
              验收通过（关闭）
            </el-button>
            <el-button v-if="user.hasPerm('ticket:edit')" size="small" type="warning" @click="doAction('accept_check', false)">
              退回处理
            </el-button>
          </template>
          <el-button v-if="user.hasPerm('ticket:edit') && detail.status !== TICKET_STATUS.CLOSED" size="small" type="info"
            plain @click="doAction('close')">关闭工单</el-button>
          <el-button v-if="user.hasPerm('ticket:edit')" size="small" type="primary" plain @click="openEdit(detail)">
            编辑
          </el-button>
          <el-button
            v-if="user.hasPerm('kb:add') && ([TICKET_STATUS.CLOSED, TICKET_STATUS.CHECKED] as string[]).includes(detail.status)"
            size="small" type="success" plain @click="onArchive">归档为知识库案例</el-button>
          <el-button v-if="user.hasPerm('ticket:delete')" size="small" type="danger" plain @click="onDelete">
            删除
          </el-button>
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
      </div>
    </el-drawer>

    <!-- 提交审核（处理报告 + 诊断/方案 + 提交备注） -->
    <el-dialog v-model="submitVisible" title="提交审核" width="560px" destroy-on-close>
      <el-form label-width="90px">
        <el-form-item label="处理报告" required>
          <el-upload ref="submitUploadRef" drag :auto-upload="false" :limit="1"
            accept=".doc,.docx,.pdf,.xlsx,.xls,.png,.jpg,.jpeg,.gif,.bmp,.webp,.zip"
            :on-change="onSubmitFileChange" :on-remove="() => submitFile = null">
            <el-icon class="el-icon--upload"><UploadFilled /></el-icon>
            <div class="el-upload__text">拖拽或点击上传处理报告（Word/PDF/Excel/图片）</div>
          </el-upload>
        </el-form-item>
        <el-form-item label="诊断分析">
          <el-input v-model="submitForm.diagnosis" type="textarea" :rows="2" placeholder="故障诊断（可选）" />
        </el-form-item>
        <el-form-item label="解决方案">
          <el-input v-model="submitForm.solution" type="textarea" :rows="3" placeholder="处置方案（可选）" />
        </el-form-item>
        <el-form-item label="提交备注">
          <el-input v-model="submitForm.note" type="textarea" :rows="2"
            placeholder="不便写入报告的实际情况（可选），将随本次提交留档" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="submitVisible = false">取消</el-button>
        <el-button type="primary" :loading="submitting" @click="doSubmit">提交审核</el-button>
      </template>
    </el-dialog>

    <!-- 审核弹窗（退回修改：原因 + 修改要求） -->
    <el-dialog v-model="auditVisible" :title="auditApproved ? '审核通过' : '退回修改'" width="520px"
      destroy-on-close>
      <el-form label-width="90px">
        <template v-if="auditApproved">
          <el-form-item label="审核意见">
            <el-input v-model="auditRemark" type="textarea" :rows="3" placeholder="审核意见（可选）" />
          </el-form-item>
        </template>
        <template v-else>
          <el-form-item label="退回原因" required>
            <el-input v-model="auditRemark" type="textarea" :rows="2"
              placeholder="如：缺少变更记录、处理方案不完整" />
          </el-form-item>
          <el-form-item label="需要修改" required>
            <el-input v-model="auditRequirements" type="textarea" :rows="3"
              placeholder="填写需要修改的内容，工程师将按此要求修改后重新提交审核" />
          </el-form-item>
        </template>
      </el-form>
      <template #footer>
        <el-button @click="auditVisible = false">取消</el-button>
        <el-button type="primary" :loading="auditing" @click="doAudit">
          {{ auditApproved ? '审核通过' : '退回修改' }}
        </el-button>
      </template>
    </el-dialog>

    <!-- 新建/编辑工单 -->
    <el-dialog v-model="formVisible" :title="form.id ? '编辑工单' : '新建工单'" width="640px" top="5vh" destroy-on-close>
      <el-form ref="formRef" :model="form" :rules="formRules" label-width="100px">
        <el-form-item label="标题" prop="title">
          <el-input v-model="form.title" placeholder="必填，如：核心交换机宕机" />
        </el-form-item>
        <el-row :gutter="12">
          <el-col :xs="24" :sm="12">
            <el-form-item label="客户">
              <el-select v-model="form.customer_id" filterable clearable class="w-full">
                <el-option v-for="c in regionCustomers" :key="c.id" :label="c.name" :value="c.id" />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :xs="24" :sm="12">
            <el-form-item label="优先级">
              <el-select v-model="form.priority" class="w-full">
                <el-option v-for="p in dicts?.priorities || []" :key="p" :label="p" :value="p" />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :xs="24" :sm="12">
            <el-form-item label="来源">
              <el-select v-model="form.source_type" class="w-full">
                <el-option v-for="s in TICKET_SOURCE_TYPES" :key="s" :label="s" :value="s" />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :xs="24" :sm="12">
            <el-form-item label="故障类型">
              <el-select v-model="form.fault_category_id" filterable allow-create clearable class="w-full">
                <el-option v-for="f in dicts?.fault_types || []" :key="f.id" :label="f.name" :value="f.id" />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :xs="24" :sm="12">
            <el-form-item label="关联设备">
              <el-select v-model="form.related_device_id" filterable clearable class="w-full"
                placeholder="按客户过滤，可搜索">
                <el-option v-for="d in filteredDevices" :key="d.id" :label="d.device_name" :value="d.id" />
              </el-select>
            </el-form-item>
          </el-col>
        </el-row>
        <el-form-item label="描述">
          <el-input v-model="form.description" type="textarea" :rows="3" />
        </el-form-item>
        <el-form-item label="处置方式">
          <el-radio-group v-model="form.dispatch_mode">
            <el-radio value="pending">待派单（调度分配）</el-radio>
            <el-radio value="self_accept">我自己接单处置</el-radio>
          </el-radio-group>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="formVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="save">{{ form.id ? '保存' : '创建' }}</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ElMessageBox } from 'element-plus/es/components/message-box/index'
import type { UploadFile } from 'element-plus/es/components/upload'
import { ref, reactive, computed, onMounted } from 'vue'
import { Plus, Search, Download, FolderOpened, UploadFilled } from '@element-plus/icons-vue'
import DataTable, { type DataColumn } from '@/components/DataTable.vue'
import VersionTimeline from '@/components/VersionTimeline.vue'
import { useUserStore } from '@/stores/user'
import { useUiStore } from '@/stores/ui'
import {
  fetchTickets, fetchTicket, createTicket, updateTicket, deleteTicket, ticketAction,
  ticketActionSubmit, fetchTicketVersions, versionReportUrl, ticketExportUrl,
  ticketReportsZipUrl, fetchTicketDicts, TICKET_STATUS_TAG, archiveTicketAsCase,
  type Ticket, type TicketDicts,
} from '@/api/tickets'
import { TICKET_STATUS, TICKET_PRIORITY_TAG, TICKET_SOURCE_TYPES } from '@/utils/status'
import type { SubmissionVersion as SV } from '@/api/inspections'

const user = useUserStore()
const ui = useUiStore()
const dicts = ref<TicketDicts | null>(null)

/** 关联设备下拉：按所选客户过滤（未选客户时展示全部） */
const filteredDevices = computed(() => {
  const list = dicts.value?.devices || []
  if (!form.customer_id) return list
  return list.filter((d) => d.customer_id === form.customer_id)
})

/** 客户下拉：驻场工程师（配置了负责区域）仅显示对应区域客户；区域无客户时兜底全部 */
const regionCustomers = computed(() => {
  const custs = dicts.value?.customers || []
  const rids = user.user?.region_ids || []
  if (!rids.length) return custs
  const filtered = custs.filter((c) => c.region_id !== null && rids.includes(c.region_id))
  return filtered.length ? filtered : custs
})

const query = reactive<Record<string, unknown>>({ search: '', status: '', priority: '', customer_id: undefined, scope: 'all' })
const dateRange = ref<[string, string] | null>(null)
const incompleteOnly = ref(false)
const tableRef = ref()

const columns = computed<DataColumn[]>(() => [
  { key: 'title', label: '标题', minWidth: 180, asTitle: true },
  { key: 'number', label: '单号', width: 130 },
  { key: 'status', label: '状态', width: 90, type: 'tag', asTag: true, tagMap: TICKET_STATUS_TAG },
  { key: 'priority', label: '优先级', width: 80, type: 'tag', tagMap: TICKET_PRIORITY_TAG },
  { key: 'customer_name', label: '客户', minWidth: 100 },
  { key: 'assigned_to', label: '处理人', width: 90 },
  { key: 'complete', label: '资料完整', width: 100, type: 'tag',
    tagMap: { true: 'success', false: 'warning' } as Record<string, 'success' | 'warning'>,
    valueMap: { true: '完整', false: '不完整' } },
  { key: 'created_at', label: '创建时间', width: 130 },
  { key: 'actions', label: '操作', width: 90, type: 'action', fixed: 'right',
    actions: [
      { label: '处理', type: 'primary', link: true, perm: 'ticket:view', icon: 'View',
        onClick: (row) => openDetail(row) },
      { label: '删除', type: 'danger', link: true, perm: 'ticket:delete', icon: 'Delete',
        onClick: (row) => onDelete(row as unknown as Ticket) },
    ] },
])

// 详情
const detailVisible = ref(false)
const detail = ref<Ticket | null>(null)
const versions = ref<SV[]>([])
const assignee = ref('')

async function openDetail(row: Record<string, unknown>) {
  try {
    const [full, vers] = await Promise.all([
      fetchTicket(row.id as number),
      fetchTicketVersions(row.id as number),
    ])
    detail.value = full
    versions.value = vers
    assignee.value = full.assigned_to || ''
    detailVisible.value = true
  } catch { /* toast */ }
}

async function refreshDetail() {
  if (!detail.value) return
  try {
    const [full, vers] = await Promise.all([
      fetchTicket(detail.value.id),
      fetchTicketVersions(detail.value.id),
    ])
    detail.value = full
    versions.value = vers
  } catch { /* toast */ }
}

function downloadLatest() {
  const latest = versions.value.slice().reverse().find((v) => v.report_file)
  if (!latest) return
  window.open(versionReportUrl('ticket', latest.id), '_blank')
}

async function doAction(action: string, approved?: boolean) {
  if (!detail.value) return
  const payload: { action: string; assignee?: string; approved?: boolean } = { action }
  if (action === 'assign') {
    if (!assignee.value.trim()) { ui.toast('请填写处理人', 'warning'); return }
    payload.assignee = assignee.value.trim()
  }
  if (typeof approved === 'boolean') payload.approved = approved
  try {
    await ticketAction(detail.value.id, payload)
    ui.toast('操作成功', 'success')
    await refreshDetail()
    tableRef.value?.refresh()
  } catch (e) {
    ui.toast((e as Error).message, 'error')
  }
}

function openAudit(approved: boolean) {
  if (!detail.value) return
  auditApproved.value = approved
  auditRemark.value = ''
  auditRequirements.value = ''
  auditVisible.value = true
}

async function doAudit() {
  if (!detail.value) return
  if (!auditApproved.value) {
    if (!auditRemark.value.trim()) {
      ui.toast('请填写退回原因', 'warning')
      return
    }
    if (!auditRequirements.value.trim()) {
      ui.toast('请填写需要修改的内容（修改要求）', 'warning')
      return
    }
  }
  auditing.value = true
  try {
    await ticketAction(detail.value.id, {
      action: 'audit',
      approved: auditApproved.value,
      remark: auditRemark.value.trim(),
      requirements: auditRequirements.value.trim(),
    })
    ui.toast(`${auditApproved.value ? '审核通过' : '退回修改'}成功`, 'success')
    auditVisible.value = false
    await refreshDetail()
    tableRef.value?.refresh()
  } catch (e) {
    ui.toast((e as Error).message, 'error')
  } finally {
    auditing.value = false
  }
}

// 提交审核（处理报告 + 诊断/方案 + 提交备注）
const submitVisible = ref(false)
const submitting = ref(false)
const submitUploadRef = ref()
const submitFile = ref<File | null>(null)
const submitForm = reactive({ diagnosis: '', solution: '', note: '' })

// 审核弹窗
const auditVisible = ref(false)
const auditApproved = ref(true)
const auditRemark = ref('')
const auditRequirements = ref('')
const auditing = ref(false)

function openSubmit() {
  submitFile.value = null
  submitForm.diagnosis = ''
  submitForm.solution = ''
  submitForm.note = ''
  submitUploadRef.value?.clearFiles?.()
  submitVisible.value = true
}

function onSubmitFileChange(f: UploadFile) {
  submitFile.value = f.raw ?? null
}

async function doSubmit() {
  if (!detail.value) return
  if (!submitFile.value) {
    ui.toast('请上传处理报告文件', 'warning')
    return
  }
  submitting.value = true
  try {
    const fd = new FormData()
    fd.append('action', 'submit')
    fd.append('report_file', submitFile.value)
    fd.append('diagnosis', submitForm.diagnosis)
    fd.append('solution', submitForm.solution)
    fd.append('note', submitForm.note)
    await ticketActionSubmit(detail.value.id, fd)
    ui.toast('已提交审核（生成提交记录）', 'success')
    submitVisible.value = false
    await refreshDetail()
    tableRef.value?.refresh()
  } catch (e) {
    ui.toast((e as Error).message, 'error')
  } finally {
    submitting.value = false
  }
}

async function onDelete(t: Ticket) {
  try {
    await ElMessageBox.confirm(`确定删除工单「${t.number}」吗？`, '删除确认', { type: 'warning' })
  } catch { return }
  try {
    await deleteTicket(t.id)
    ui.toast('已删除', 'success')
    detailVisible.value = false
    tableRef.value?.refresh()
  } catch (e) {
    ui.toast((e as Error).message, 'error')
  }
}

// 新建
const formVisible = ref(false)
const saving = ref(false)
const formRef = ref()
const form = reactive<Record<string, unknown>>({
  id: null, title: '', customer_id: null, priority: '中', source_type: '手动创建',
  fault_category_id: null, related_device_id: null, description: '', dispatch_mode: 'pending',
})
const formRules = { title: [{ required: true, message: '请输入工单标题', trigger: 'blur' }] }

function openCreate() {
  Object.assign(form, { id: null, title: '', customer_id: null, priority: '中', source_type: '手动创建',
    fault_category_id: null, related_device_id: null, description: '', dispatch_mode: 'pending' })
  // 驻场工程师：默认选中负责区域的第一个客户（无负责区域用户不受影响）
  const first = regionCustomers.value[0]
  if (first && !form.customer_id) form.customer_id = first.id
  formVisible.value = true
}

function openEdit(t: Ticket) {
  Object.assign(form, {
    id: t.id, title: t.title, customer_id: t.customer_id, priority: t.priority,
    source_type: t.source_type || '手动创建', fault_category_id: t.fault_category_id,
    related_device_id: t.related_device_id, description: t.description, dispatch_mode: 'pending',
  })
  formVisible.value = true
}

async function save() {
  try { await formRef.value?.validate() } catch { return }
  saving.value = true
  try {
    if (form.id) {
      await updateTicket(form.id as number, { ...form })
      ui.toast('工单已更新', 'success')
      formVisible.value = false
      await refreshDetail()
    } else {
      const res = await createTicket({ ...form })
      ui.toast(`工单 ${res.number} 已创建${form.dispatch_mode === 'self_accept' ? '，已由你接单' : ''}`, 'success')
      formVisible.value = false
    }
    tableRef.value?.refresh()
  } catch (e) {
    ui.toast((e as Error).message, 'error')
  } finally {
    saving.value = false
  }
}

async function onArchive() {
  if (!detail.value) return
  try {
    await ElMessageBox.confirm('归档后生成知识库案例（内容来自诊断/方案/描述），继续吗？', '归档确认',
      { type: 'info' })
  } catch { return }
  try {
    const res = await archiveTicketAsCase(detail.value.id)
    ui.toast(`已归档为知识库案例 #${res.id}`, 'success')
  } catch (e) {
    ui.toast((e as Error).message, 'error')
  }
}

// 筛选 + 导出
function onDateChange(val: [string, string] | null) {
  query.date_from = val?.[0] ?? undefined
  query.date_to = val?.[1] ?? undefined
  reload()
}

function exportParams() {
  return {
    customer_id: query.customer_id as number | undefined,
    date_from: query.date_from as string | undefined,
    date_to: query.date_to as string | undefined,
  }
}

function doExport(kind: 'excel' | 'zip') {
  const url = kind === 'excel' ? ticketExportUrl(exportParams()) : ticketReportsZipUrl(exportParams())
  window.open(url, '_blank')
}

function reload() {
  query.incomplete_only = incompleteOnly.value ? 1 : undefined
  tableRef.value?.refresh()
}

onMounted(() => {
  fetchTicketDicts().then((d) => (dicts.value = d))
})
</script>

<style scoped>
.filter-card { margin-bottom: 12px; }
.filter-row { display: flex; gap: 8px; flex-wrap: wrap; align-items: center; }
.filter-search { width: 180px; max-width: 100%; }
.filter-item { width: 130px; max-width: 100%; }
.date-range { width: 240px; }
.header-actions { display: flex; gap: 8px; flex-wrap: wrap; }
.w-full { width: 100%; }
.detail-text { white-space: pre-wrap; word-break: break-all; font-size: 13px; }
.review-comment { color: var(--el-color-danger); font-weight: 600; white-space: pre-wrap; }
.review-meta { font-size: 12px; color: var(--itsm-text-muted); display: flex; align-items: center; gap: 6px; }
.audit-tag { margin-left: 4px; }
.action-bar { display: flex; gap: 8px; flex-wrap: wrap; align-items: center; }
.assign-input { width: 160px; }
.log-item { font-size: 13px; }
.log-op { color: var(--itsm-text-muted); margin-left: 8px; font-size: 12px; }
.log-comment { color: var(--itsm-text-muted); font-size: 12px; margin-top: 2px; }
.text-muted { color: var(--itsm-text-muted); }
</style>
