<template>
  <div class="page-container">
    <div class="page-header">
      <h2 class="page-title">工单管理</h2>
      <div class="header-actions">
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
        <el-checkbox v-model="query.scope" true-label="mine" false-label="all" @change="reload">
          只看我的
        </el-checkbox>
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
      size="560px" destroy-on-close>
      <div v-if="detail">
        <el-descriptions :column="2" border size="small">
          <el-descriptions-item label="状态">
            <el-tag size="small" :type="TICKET_STATUS_TAG[detail.status] || 'info'">{{ detail.status }}</el-tag>
          </el-descriptions-item>
          <el-descriptions-item label="优先级">
            <el-tag size="small" :type="detail.priority === '紧急' ? 'danger' : 'warning'">{{ detail.priority }}</el-tag>
          </el-descriptions-item>
          <el-descriptions-item label="客户">{{ detail.customer_name || '-' }}</el-descriptions-item>
          <el-descriptions-item label="处理人">{{ detail.assigned_to || '-' }}</el-descriptions-item>
          <el-descriptions-item label="创建人">{{ detail.created_by || '-' }}</el-descriptions-item>
          <el-descriptions-item label="创建时间">{{ detail.created_at }}</el-descriptions-item>
          <el-descriptions-item label="来源">{{ detail.source_type || '-' }}</el-descriptions-item>
          <el-descriptions-item label="严重级别">{{ detail.severity_level || '-' }}</el-descriptions-item>
        </el-descriptions>

        <el-divider content-position="left">描述</el-divider>
        <p class="detail-text">{{ detail.description || '-' }}</p>

        <template v-if="detail.diagnosis || detail.solution">
          <el-divider content-position="left">处理方案</el-divider>
          <p class="detail-text"><b>诊断：</b>{{ detail.diagnosis || '-' }}</p>
          <p class="detail-text"><b>方案：</b>{{ detail.solution || '-' }}</p>
        </template>

        <!-- 状态机操作 -->
        <el-divider content-position="left">操作</el-divider>
        <div class="action-bar">
          <template v-if="detail.status === '待派单'">
            <el-input v-model="assignee" placeholder="处理人姓名" class="assign-input" size="small" />
            <el-button v-if="user.hasPerm('ticket:edit')" size="small" type="primary" @click="doAction('assign')">
              派单
            </el-button>
            <el-button v-if="user.hasPerm('ticket:edit')" size="small" type="warning" @click="doAction('close')">
              关闭
            </el-button>
          </template>
          <template v-else-if="detail.status === '已派单'">
            <el-button v-if="user.hasPerm('ticket:edit')" size="small" type="success" @click="doAction('accept')">
              接单（开始处理）
            </el-button>
          </template>
          <template v-else-if="detail.status === '处理中'">
            <el-button v-if="user.hasPerm('ticket:edit')" size="small" type="primary" @click="openSubmit">
              提交审核
            </el-button>
          </template>
          <template v-else-if="detail.status === '待审核'">
            <el-button v-if="user.hasPerm('ticket:edit')" size="small" type="success" @click="doAction('audit', true)">
              审核通过
            </el-button>
            <el-button v-if="user.hasPerm('ticket:edit')" size="small" type="danger" @click="doAction('audit', false)">
              退回
            </el-button>
          </template>
          <template v-else-if="detail.status === '已验收'">
            <el-button v-if="user.hasPerm('ticket:edit')" size="small" type="success" @click="doAction('accept_check', true)">
              验收通过（关闭）
            </el-button>
            <el-button v-if="user.hasPerm('ticket:edit')" size="small" type="warning" @click="doAction('accept_check', false)">
              退回处理
            </el-button>
          </template>
          <el-button v-if="user.hasPerm('ticket:edit') && detail.status !== '已关闭'" size="small" type="info"
            plain @click="doAction('close')">关闭工单</el-button>
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

    <!-- 新建工单 -->
    <el-dialog v-model="formVisible" title="新建工单" width="640px" top="5vh" destroy-on-close>
      <el-form ref="formRef" :model="form" :rules="formRules" label-width="100px">
        <el-form-item label="标题" prop="title">
          <el-input v-model="form.title" placeholder="必填，如：核心交换机宕机" />
        </el-form-item>
        <el-row :gutter="12">
          <el-col :xs="24" :sm="12">
            <el-form-item label="客户">
              <el-select v-model="form.customer_id" filterable clearable class="w-full">
                <el-option v-for="c in dicts?.customers || []" :key="c.id" :label="c.name" :value="c.id" />
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
                <el-option v-for="s in ['客户报修','巡检发现','手动创建','定期维护']" :key="s" :label="s" :value="s" />
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
        <el-button type="primary" :loading="saving" @click="save">创建</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onMounted } from 'vue'
import { ElMessageBox } from 'element-plus'
import { Plus, Search } from '@element-plus/icons-vue'
import DataTable, { type DataColumn } from '@/components/DataTable.vue'
import { useUserStore } from '@/stores/user'
import { useUiStore } from '@/stores/ui'
import {
  fetchTickets, fetchTicket, createTicket, deleteTicket, ticketAction,
  fetchTicketDicts, TICKET_STATUS_TAG, type Ticket, type TicketDicts,
} from '@/api/tickets'

const user = useUserStore()
const ui = useUiStore()
const dicts = ref<TicketDicts | null>(null)

const query = reactive<Record<string, unknown>>({ search: '', status: '', priority: '', customer_id: undefined, scope: 'all' })
const tableRef = ref()

const columns = computed<DataColumn[]>(() => [
  { key: 'title', label: '标题', type: 'link', minWidth: 180, asTitle: true,
    link: (r) => `/app/tickets/${r.id}` },
  { key: 'number', label: '单号', width: 130 },
  { key: 'status', label: '状态', width: 90, type: 'tag', asTag: true, tagMap: TICKET_STATUS_TAG },
  { key: 'priority', label: '优先级', width: 80, type: 'tag',
    tagMap: { 紧急: 'danger', 高: 'warning', 中: 'info', 低: 'info' } },
  { key: 'customer_name', label: '客户', minWidth: 100 },
  { key: 'assigned_to', label: '处理人', width: 90 },
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
const assignee = ref('')

async function openDetail(row: Record<string, unknown>) {
  try {
    detail.value = await fetchTicket(row.id as number)
    assignee.value = detail.value.assigned_to || ''
    detailVisible.value = true
  } catch { /* toast */ }
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
    detail.value = await fetchTicket(detail.value.id)
    tableRef.value?.refresh()
  } catch (e) {
    ui.toast((e as Error).message, 'error')
  }
}

function openSubmit() {
  ElMessageBox.prompt('提交审核（可填写处理方案）', '提交审核', {
    inputType: 'textarea', inputPlaceholder: '诊断分析与解决方案（可选）',
  }).then(async ({ value }) => {
    if (!detail.value) return
    try {
      const parts = (value || '').split('\n').filter(Boolean)
      await ticketAction(detail.value.id, {
        action: 'submit',
        diagnosis: parts[0] || '',
        solution: parts.slice(1).join('\n') || '',
      })
      ui.toast('已提交审核', 'success')
      detail.value = await fetchTicket(detail.value.id)
      tableRef.value?.refresh()
    } catch (e) {
      ui.toast((e as Error).message, 'error')
    }
  }).catch(() => {})
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
  title: '', customer_id: null, priority: '中', source_type: '手动创建',
  fault_category_id: null, description: '', dispatch_mode: 'pending',
})
const formRules = { title: [{ required: true, message: '请输入工单标题', trigger: 'blur' }] }

function openCreate() {
  Object.assign(form, { title: '', customer_id: null, priority: '中', source_type: '手动创建',
    fault_category_id: null, description: '', dispatch_mode: 'pending' })
  formVisible.value = true
}

async function save() {
  try { await formRef.value?.validate() } catch { return }
  saving.value = true
  try {
    const res = await createTicket({ ...form })
    ui.toast(`工单 ${res.number} 已创建${form.dispatch_mode === 'self_accept' ? '，已由你接单' : ''}`, 'success')
    formVisible.value = false
    tableRef.value?.refresh()
  } catch (e) {
    ui.toast((e as Error).message, 'error')
  } finally {
    saving.value = false
  }
}

function reload() { tableRef.value?.refresh() }

onMounted(() => {
  fetchTicketDicts().then((d) => (dicts.value = d))
})
</script>

<style scoped>
.filter-card { margin-bottom: 12px; }
.filter-row { display: flex; gap: 8px; flex-wrap: wrap; align-items: center; }
.filter-search { width: 200px; max-width: 100%; }
.filter-item { width: 130px; max-width: 100%; }
.header-actions { display: flex; gap: 8px; flex-wrap: wrap; }
.w-full { width: 100%; }
.detail-text { white-space: pre-wrap; word-break: break-all; font-size: 13px; }
.action-bar { display: flex; gap: 8px; flex-wrap: wrap; align-items: center; }
.assign-input { width: 160px; }
.log-item { font-size: 13px; }
.log-op { color: var(--itsm-text-muted); margin-left: 8px; font-size: 12px; }
.log-comment { color: var(--itsm-text-muted); font-size: 12px; margin-top: 2px; }
</style>
