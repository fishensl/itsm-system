<template>
  <div class="page-container">
    <div class="page-header">
      <h2 class="page-title">任务安排</h2>
      <div class="header-actions">
        <el-button plain :icon="Download" @click="downloadTemplate">导入模板</el-button>
        <input ref="importInput" type="file" accept=".xlsx,.xls" style="display: none" @change="onImportFile" />
        <el-button plain :icon="Upload" @click="importInput?.click()">批量导入</el-button>
        <el-button v-if="user.hasPerm('task:schedule')" type="primary" :icon="Plus" @click="openCreate">
          快速新建
        </el-button>
      </div>
    </div>

    <!-- KPI -->
    <el-row v-if="data" :gutter="8" class="kpi-row">
      <el-col v-for="k in kpiCards" :key="k.key" :xs="12" :sm="8" :md="3">
        <div class="kpi-card" :class="k.cls">
          <div class="kpi-value">{{ k.value }}</div>
          <div class="kpi-label">{{ k.label }}</div>
        </div>
      </el-col>
    </el-row>

    <!-- 筛选 -->
    <el-card shadow="never" class="filter-card">
      <div class="filter-row">
        <el-radio-group v-model="query.view" size="small" @change="reload">
          <el-radio-button value="status">按状态</el-radio-button>
          <el-radio-button value="engineer">按工程师</el-radio-button>
        </el-radio-group>
        <el-radio-group v-model="query.period" size="small" @change="reload">
          <el-radio-button value="this_month">当月</el-radio-button>
          <el-radio-button value="this_quarter">本季</el-radio-button>
          <el-radio-button value="this_year">本年</el-radio-button>
          <el-radio-button value="">全部</el-radio-button>
        </el-radio-group>
        <el-input v-model="query.q" placeholder="搜索任务" clearable size="small" style="width: 180px"
          @keyup.enter="reload" @clear="reload" />
        <el-select v-model="query.customer_id" placeholder="客户" clearable filterable size="small"
          style="width: 160px" @change="reload">
          <el-option v-for="c in data?.customers || []" :key="c.id" :label="c.name" :value="c.id" />
        </el-select>
        <el-checkbox v-model="onlyOverdue" size="small" @change="toggleOverdue">仅逾期</el-checkbox>
        <el-button type="primary" plain size="small" :icon="Search" @click="reload">查询</el-button>
      </div>
    </el-card>

    <!-- 批量操作条 -->
    <div v-if="selectedIds.length" class="batch-bar">
      <span>已选 {{ selectedIds.length }} 项</span>
      <el-select v-model="batchStatus" placeholder="批量改状态" size="small" style="width: 140px"
        @change="runBatch('status', batchStatus)">
        <el-option v-for="s in ['待执行', '执行中', '已完成', '已取消']" :key="s" :label="s" :value="s" />
      </el-select>
      <el-select v-model="batchAssignee" placeholder="批量指派" clearable filterable size="small" style="width: 160px"
        @change="runBatch('assign', batchAssignee)">
        <el-option v-for="e in data?.engineers || []" :key="e.id" :label="e.name" :value="e.id" />
      </el-select>
      <el-button size="small" type="danger" plain @click="runBatch('delete')">批量删除</el-button>
      <el-button size="small" @click="selectedIds = []">取消选择</el-button>
    </div>

    <!-- 按状态视图 -->
    <div v-if="data?.view === 'status'" class="board-cols">
      <div v-for="st in ['待执行', '执行中', '已完成']" :key="st" class="board-col">
        <div class="col-head" :class="`col-${st}`">
          {{ st }}
          <span class="col-count">{{ data.status_groups?.[st]?.length || 0 }}</span>
        </div>
        <div class="col-body">
          <el-checkbox v-if="(data.status_groups?.[st] || []).length" class="col-check"
            :model-value="selectedIds.length > 0 && (data.status_groups?.[st] || []).every((t) => selectedIds.includes(t.id))"
            @change="(v: boolean | string | number | undefined) => toggleCol(st, !!v)">
            全选
          </el-checkbox>
          <div v-for="t in data.status_groups?.[st] || []" :key="t.id" class="task-card"
            :class="{ overdue: t.overdue, selected: selectedIds.includes(t.id) }"
            @click="openDetail(t)">
            <el-checkbox class="task-check" :model-value="selectedIds.includes(t.id)"
              @click.stop @change="(v: boolean | string | number | undefined) => toggleSelect(t.id, !!v)" />
            <div class="task-title">{{ t.title }}</div>
            <div class="task-meta">
              <el-tag v-if="t.overdue" size="small" type="danger" effect="dark">逾期</el-tag>
              <el-tag size="small" :type="priorityType(t.priority)" effect="dark">{{ t.priority }}</el-tag>
              <el-tag v-if="t.task_type === '突发'" size="small" type="warning" effect="dark">突发</el-tag>
            </div>
            <div class="task-sub">{{ t.customer_name || '-' }}</div>
            <div class="task-sub">
              <span>{{ t.assignee_name || '未指派' }}</span>
              <span v-if="t.planned_end" class="float-right">{{ t.planned_end }}</span>
            </div>
          </div>
          <el-empty v-if="!(data.status_groups?.[st] || []).length" description="无任务" :image-size="40" />
        </div>
      </div>
    </div>

    <!-- 按工程师视图 -->
    <div v-else-if="data?.view === 'engineer'" class="board-cols">
      <div v-for="e in [...(data.engineers || []), { id: '__unassigned__', name: '未指派' }]" :key="e.id"
        class="board-col">
        <div class="col-head col-engineer">
          {{ e.name }}
          <span class="col-count">{{ data.engineer_groups?.[String(e.id)]?.length || 0 }}</span>
        </div>
        <div class="col-body">
          <div v-for="t in data.engineer_groups?.[String(e.id)] || []" :key="t.id" class="task-card"
            :class="{ overdue: t.overdue }" @click="openDetail(t)">
            <div class="task-title">{{ t.title }}</div>
            <div class="task-meta">
              <el-tag v-if="t.overdue" size="small" type="danger" effect="dark">逾期</el-tag>
              <el-tag size="small" :type="statusType(t.status)" effect="dark">{{ t.status }}</el-tag>
            </div>
            <div class="task-sub">{{ t.customer_name || '-' }} · {{ t.planned_end || '-' }}</div>
          </div>
          <el-empty v-if="!(data.engineer_groups?.[String(e.id)] || []).length" description="无任务" :image-size="40" />
        </div>
      </div>
    </div>

    <!-- 快速新建 -->
    <el-dialog v-model="createVisible" title="快速新建任务" width="520px" destroy-on-close>
      <el-form ref="createFormRef" :model="createForm" label-width="90px">
        <el-form-item label="任务描述" prop="title" :rules="[{ required: true, message: '请输入', trigger: 'blur' }]">
          <el-input v-model="createForm.title" placeholder="如：XX 客户 2026 年三季度巡检" />
        </el-form-item>
        <el-form-item label="客户" prop="customer_id" :rules="[{ required: true, message: '请选择', trigger: 'change' }]">
          <el-select v-model="createForm.customer_id" filterable style="width: 100%">
            <el-option v-for="c in data?.customers || []" :key="c.id" :label="c.name" :value="c.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="负责人">
          <el-select v-model="createForm.assignee_id" clearable filterable style="width: 100%">
            <el-option v-for="e in data?.engineers || []" :key="e.id" :label="e.name" :value="e.id" />
          </el-select>
        </el-form-item>
        <el-row :gutter="12">
          <el-col :span="12">
            <el-form-item label="开始日期">
              <el-date-picker v-model="createForm.planned_start" type="date" value-format="YYYY-MM-DD"
                style="width: 100%" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="完成日期">
              <el-date-picker v-model="createForm.planned_end" type="date" value-format="YYYY-MM-DD"
                style="width: 100%" />
            </el-form-item>
          </el-col>
        </el-row>
        <el-row :gutter="12">
          <el-col :span="12">
            <el-form-item label="优先级">
              <el-select v-model="createForm.priority" style="width: 100%">
                <el-option v-for="p in ['低', '中', '高', '紧急']" :key="p" :label="p" :value="p" />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="预估人天">
              <el-input-number v-model="createForm.estimated_effort" :min="0" :step="0.5" style="width: 100%" />
            </el-form-item>
          </el-col>
        </el-row>
        <el-form-item label="任务类型">
          <el-radio-group v-model="createForm.task_type">
            <el-radio value="计划">计划</el-radio>
            <el-radio value="突发">突发</el-radio>
          </el-radio-group>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="createVisible = false">取消</el-button>
        <el-button type="primary" :loading="creating" @click="doCreate">创建</el-button>
      </template>
    </el-dialog>

    <!-- 详情 -->
    <el-drawer v-model="detailVisible" :title="detail ? detail.title : ''" size="480px">
      <template v-if="detail">
        <el-form label-width="90px">
          <el-form-item label="状态">
            <el-select :model-value="detail.status" size="small" style="width: 160px"
              @change="(v: string) => quickUpdate({ status: v })">
              <el-option v-for="s in ['待执行', '执行中', '已完成', '已取消']" :key="s" :label="s" :value="s" />
            </el-select>
          </el-form-item>
          <el-form-item label="负责人">
            <el-select :model-value="detail.assignee_id" clearable filterable size="small" style="width: 160px"
              @change="(v: number | undefined) => quickUpdate({ assignee_id: v ?? null })">
              <el-option v-for="e in data?.engineers || []" :key="e.id" :label="e.name" :value="e.id" />
            </el-select>
          </el-form-item>
          <el-form-item label="客户">{{ detail.customer_name || '-' }}</el-form-item>
          <el-form-item label="计划时间">
            <el-date-picker :model-value="detail.planned_start" type="date" value-format="YYYY-MM-DD"
              size="small" style="width: 140px" @change="(v: string) => quickUpdate({ planned_start: v || null })" />
            <span class="mx-1">~</span>
            <el-date-picker :model-value="detail.planned_end" type="date" value-format="YYYY-MM-DD"
              size="small" style="width: 140px" @change="(v: string) => quickUpdate({ planned_end: v || null })" />
          </el-form-item>
          <el-form-item label="预估人天">
            <el-input-number :model-value="detail.estimated_effort ?? undefined" :min="0" :step="0.5" size="small"
              style="width: 120px" @change="(v: number | undefined) => quickUpdate({ estimated_effort: v ?? null })" />
          </el-form-item>
          <el-form-item label="实际人天">
            <el-input-number :model-value="detail.actual_effort ?? undefined" :min="0" :step="0.5" size="small"
              style="width: 120px" @change="(v: number | undefined) => quickUpdate({ actual_effort: v ?? null })" />
          </el-form-item>
          <el-form-item label="来源">{{ detail.source || '-' }}</el-form-item>
          <el-form-item label="备注">
            <el-input :model-value="detail.remark" type="textarea" :rows="2" size="small"
              @blur="(e: FocusEvent) => quickUpdate({ remark: (e.target as HTMLInputElement).value })" />
          </el-form-item>
        </el-form>
        <el-button type="danger" plain :loading="deleting" @click="onDelete(detail)">删除任务</el-button>
      </template>
    </el-drawer>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onMounted } from 'vue'
import { ElMessageBox } from 'element-plus'
import { Plus, Search, Download, Upload } from '@element-plus/icons-vue'
import {
  fetchTaskSchedule, createTaskSchedule, updateTaskSchedule, deleteTaskSchedule,
  batchTaskSchedule, fetchImportTemplate, importTaskSchedule, downloadBase64,
  type TaskScheduleData, type TaskScheduleItem,
} from '@/api/taskSchedule'
import { useUserStore } from '@/stores/user'
import { useUiStore } from '@/stores/ui'

const user = useUserStore()
const ui = useUiStore()
const data = ref<TaskScheduleData | null>(null)
const loading = ref(false)
const query = reactive<Record<string, unknown>>({ view: 'status', period: 'this_quarter', q: '' })
const onlyOverdue = ref(false)
const selectedIds = ref<number[]>([])
const batchStatus = ref('')
const batchAssignee = ref<number | null>(null)

const createVisible = ref(false)
const creating = ref(false)
const createFormRef = ref()
const createForm = reactive<Record<string, unknown>>({
  title: '', customer_id: undefined, assignee_id: null, planned_start: '', planned_end: '',
  priority: '中', estimated_effort: null, task_type: '计划', remark: '',
})

const detailVisible = ref(false)
const detail = ref<TaskScheduleItem | null>(null)
const deleting = ref(false)
const importInput = ref<HTMLInputElement>()

const kpiCards = computed(() => {
  const k = data.value?.kpi
  if (!k) return []
  return [
    { key: 'total', label: '总任务', value: k.total, cls: '' },
    { key: 'pending', label: '待执行', value: k.pending, cls: 'warning' },
    { key: 'running', label: '执行中', value: k.running, cls: 'primary' },
    { key: 'done', label: '已完成', value: k.done, cls: 'success' },
    { key: 'overdue', label: '逾期', value: k.overdue, cls: 'danger' },
    { key: 'est', label: '预估人天', value: k.est_effort, cls: '' },
    { key: 'act', label: '实际人天', value: k.act_effort, cls: '' },
  ]
})

function priorityType(p: string) {
  return { 低: 'info', 中: '', 高: 'warning', 紧急: 'danger' }[p] || 'info'
}

// 任务状态配色：待执行=橙 / 执行中=深蓝 / 已完成=绿 / 已取消=灰；红色留给「逾期」
// 统一 effect="dark"（深底白字）：浅色模式下对比度也足够，深浅模式表现一致
function statusType(s: string) {
  return { 待执行: 'warning', 执行中: 'primary', 已完成: 'success', 已取消: 'info' }[s] || 'info'
}

function reload() {
  const params: Record<string, unknown> = { ...query }
  if (onlyOverdue.value) params.overdue = '1'
  loading.value = true
  fetchTaskSchedule(params as never)
    .then((d) => { data.value = d })
    .catch(() => { /* toast */ })
    .finally(() => { loading.value = false })
}

function toggleOverdue(v: boolean | string | number | undefined) {
  onlyOverdue.value = !!v
  reload()
}

function toggleSelect(id: number, on: boolean) {
  const s = new Set(selectedIds.value)
  if (on) s.add(id)
  else s.delete(id)
  selectedIds.value = [...s]
}

function toggleCol(status: string, on: boolean) {
  const ids = (data.value?.status_groups?.[status] || []).map((t) => t.id)
  const s = new Set(selectedIds.value)
  if (on) ids.forEach((id) => s.add(id))
  else ids.forEach((id) => s.delete(id))
  selectedIds.value = [...s]
}

async function runBatch(action: 'status' | 'assign' | 'delete', value?: unknown) {
  if (action === 'delete') {
    try {
      await ElMessageBox.confirm(`确定删除选中的 ${selectedIds.value.length} 个任务吗？`, '批量删除', { type: 'warning' })
    } catch { return }
  }
  try {
    await batchTaskSchedule(selectedIds.value, action, value ?? null)
    ui.toast('已执行', 'success')
    selectedIds.value = []
    batchStatus.value = ''
    batchAssignee.value = null
    reload()
  } catch (e) {
    ui.toast((e as Error).message, 'error')
  }
}

function openCreate() {
  Object.assign(createForm, {
    title: '', customer_id: undefined, assignee_id: null, planned_start: '', planned_end: '',
    priority: '中', estimated_effort: null, task_type: '计划', remark: '',
  })
  createVisible.value = true
}

async function doCreate() {
  try { await createFormRef.value?.validate() } catch { return }
  creating.value = true
  try {
    await createTaskSchedule({ ...createForm })
    ui.toast('已创建', 'success')
    createVisible.value = false
    reload()
  } catch (e) {
    ui.toast((e as Error).message, 'error')
  } finally {
    creating.value = false
  }
}

function openDetail(t: TaskScheduleItem) {
  detail.value = t
  detailVisible.value = true
}

async function quickUpdate(patch: Record<string, unknown>) {
  if (!detail.value) return
  const prev = detail.value
  detail.value = { ...prev, ...patch }
  try {
    await updateTaskSchedule(prev.id, patch)
    reload()
  } catch (e) {
    detail.value = prev
    ui.toast((e as Error).message, 'error')
  }
}

async function onDelete(t: TaskScheduleItem) {
  try {
    await ElMessageBox.confirm(`确定删除任务「${t.title}」吗？`, '删除确认', { type: 'warning' })
  } catch { return }
  deleting.value = true
  try {
    await deleteTaskSchedule(t.id)
    ui.toast('已删除', 'success')
    detailVisible.value = false
    reload()
  } catch (e) {
    ui.toast((e as Error).message, 'error')
  } finally {
    deleting.value = false
  }
}

async function downloadTemplate() {
  try {
    const r = await fetchImportTemplate()
    downloadBase64(r.content, r.filename)
  } catch (e) {
    ui.toast((e as Error).message, 'error')
  }
}

async function onImportFile() {
  const file = importInput.value?.files?.[0]
  if (!file) return
  try {
    const fd = new FormData()
    fd.append('importFile', file)
    const r = await importTaskSchedule(fd)
    ui.toast(r.message, 'success')
    reload()
  } catch (e) {
    ui.toast((e as Error).message, 'error')
  } finally {
    if (importInput.value) importInput.value.value = ''
  }
}

onMounted(reload)
</script>

<style scoped>
.kpi-row { margin-bottom: 12px; }
.kpi-card {
  border: 1px solid var(--itsm-border); border-radius: 8px; padding: 10px; text-align: center;
  background: var(--itsm-card-bg); margin-bottom: 8px;
}
.kpi-card.danger .kpi-value { color: var(--el-color-danger); }
.kpi-card.warning .kpi-value { color: var(--el-color-warning); }
.kpi-card.primary .kpi-value { color: var(--el-color-primary); }
.kpi-card.success .kpi-value { color: var(--el-color-success); }
.kpi-value { font-size: 20px; font-weight: 700; }
.kpi-label { font-size: 12px; color: var(--itsm-text-muted); }
.filter-card { margin-bottom: 12px; }
.filter-row { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
.batch-bar {
  display: flex; gap: 8px; align-items: center; padding: 8px 12px; margin-bottom: 12px;
  background: var(--el-color-primary-light-9); border: 1px solid var(--el-color-primary-light-5);
  border-radius: 8px; font-size: 13px;
}
.board-cols { display: flex; gap: 12px; align-items: flex-start; overflow-x: auto; }
.board-col {
  flex: 1; min-width: 260px; border: 1px solid var(--itsm-border); border-radius: 10px;
  background: var(--itsm-card-bg); overflow: hidden;
}
.col-head {
  padding: 8px 12px; font-weight: 600; font-size: 14px; display: flex; align-items: center; gap: 6px;
}
.col-待执行 { color: var(--el-color-warning); border-bottom: 3px solid var(--el-color-warning); }
.col-执行中 { color: var(--el-color-primary); border-bottom: 3px solid var(--el-color-primary); }
.col-已完成 { color: var(--el-color-success); border-bottom: 3px solid var(--el-color-success); }
.col-engineer { border-bottom: 3px solid var(--el-color-info); }
.col-count { font-size: 12px; color: var(--itsm-text-muted); }
.col-check { margin: 6px 12px; }
.col-body { padding: 6px 10px 12px; min-height: 80px; }
.task-card {
  border: 1px solid var(--itsm-border); border-radius: 8px; padding: 8px 10px; margin-bottom: 8px;
  cursor: pointer; transition: border-color 0.15s;
  display: flex; flex-direction: column; gap: 4px;
}
.task-card:hover { border-color: var(--itsm-primary); }
.task-card.overdue { border-color: var(--el-color-danger); }
.task-card.selected { background: var(--el-color-primary-light-9); }
.task-check { position: absolute; margin-top: 2px; }
.task-title { font-size: 13px; font-weight: 600; padding-left: 24px; }
.task-meta { display: flex; gap: 4px; flex-wrap: wrap; padding-left: 24px; }
.task-sub { font-size: 12px; color: var(--itsm-text-muted); display: flex; justify-content: space-between; }
.float-right { float: right; }
.mx-1 { margin: 0 4px; }
</style>
