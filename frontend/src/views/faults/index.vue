<template>
  <div class="page-container">
    <div class="page-header">
      <h2 class="page-title">故障记录</h2>
      <div class="header-actions">
        <el-button :icon="Download" plain @click="exportVisible = true">导出</el-button>
        <el-button v-if="user.hasPerm('fault:add')" type="primary" :icon="Plus" @click="openCreate">
          新建故障
        </el-button>
      </div>
    </div>

    <!-- V24 导出筛选 -->
    <ExportDialog v-model="exportVisible" module="fault" title="导出故障记录"
      @submit="onExportSubmit" />

    <!-- 筛选 -->
    <el-card shadow="never" class="filter-card">
      <div class="filter-row">
        <el-input v-model="query.search" placeholder="搜索标题" clearable class="filter-search"
          @keyup.enter="reload" @clear="reload" />
        <el-select v-model="query.fault_type" placeholder="故障类型" clearable class="filter-item" @change="reload">
          <el-option v-for="t in dicts?.fault_types || []" :key="t.id" :label="t.name" :value="t.name" />
        </el-select>
        <el-select v-model="query.result" placeholder="处理结果" clearable class="filter-item" @change="reload">
          <el-option v-for="r in dicts?.results || []" :key="r" :label="r" :value="r" />
        </el-select>
        <el-button type="primary" plain :icon="Search" @click="reload">查询</el-button>
      </div>
    </el-card>

    <!-- 列表（点击行内展开详情） -->
    <DataTable
      ref="tableRef"
      :columns="columns"
      :fetch-data="fetchFaults"
      :query="query"
      row-key="id"
      expandable
    >
      <template #expand="{ row }">
        <FaultExpandRow
          :row="row"
          @edit="openEdit(row as unknown as Fault)"
          @delete="onDelete(row as unknown as Fault)"
        />
      </template>
    </DataTable>

    <!-- 新建/编辑故障 -->
    <el-dialog v-model="formVisible" :title="form.id ? '编辑故障' : '新建故障'" width="680px" top="5vh"
      destroy-on-close>
      <el-form ref="formRef" :model="form" :rules="formRules" label-width="90px">
        <el-form-item label="标题" prop="title">
          <el-input v-model="form.title" placeholder="必填，如：核心交换机主备切换异常" />
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
            <el-form-item label="处理人">
              <el-input v-model="form.handler" placeholder="默认当前用户" />
            </el-form-item>
          </el-col>
          <el-col :xs="24" :sm="12">
            <el-form-item label="故障时间">
              <el-date-picker v-model="form.fault_time" type="datetime" value-format="YYYY-MM-DDTHH:mm"
                class="w-full" placeholder="发生时间" />
            </el-form-item>
          </el-col>
          <el-col :xs="24" :sm="12">
            <el-form-item label="故障类型">
              <el-select v-model="form.fault_type" filterable allow-create clearable class="w-full">
                <el-option v-for="t in dicts?.fault_types || []" :key="t.id" :label="t.name" :value="t.name" />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :xs="24" :sm="12">
            <el-form-item label="处理结果">
              <el-select v-model="form.result" class="w-full">
                <el-option v-for="r in dicts?.results || []" :key="r" :label="r" :value="r" />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :xs="24" :sm="12">
            <el-form-item label="恢复时间">
              <el-date-picker v-model="form.recovery_time" type="datetime" value-format="YYYY-MM-DDTHH:mm"
                class="w-full" placeholder="恢复时间（可选）" />
            </el-form-item>
          </el-col>
        </el-row>
        <el-form-item label="故障描述">
          <el-input v-model="form.fault_description" type="textarea" :rows="3" />
        </el-form-item>
        <el-form-item label="故障原因">
          <el-input v-model="form.fault_cause" type="textarea" :rows="3" />
        </el-form-item>
        <el-form-item label="解决方案">
          <el-input v-model="form.solution" type="textarea" :rows="3" />
        </el-form-item>
        <el-form-item label="影响范围">
          <el-input v-model="form.impact_range" placeholder="如：XX 业务中断 30 分钟" />
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
import { ref, reactive, computed, onMounted } from 'vue'
import { Plus, Search, Download } from '@element-plus/icons-vue'
import DataTable, { type DataColumn } from '@/components/DataTable.vue'
import ExportDialog from '@/components/ExportDialog.vue'
import FaultExpandRow from './FaultExpandRow.vue'
import { useUserStore } from '@/stores/user'
import { useUiStore } from '@/stores/ui'
import {
  fetchFaults, fetchFault, createFault, updateFault, deleteFault, convertFaultToTicket,
  fetchFaultDicts, exportFaults, FAULT_RESULT_TAG, type Fault, type FaultDicts,
} from '@/api/faults'

const user = useUserStore()
const ui = useUiStore()
const dicts = ref<FaultDicts | null>(null)

// V24 导出筛选
const exportVisible = ref(false)

function saveBase64(b64: string, filename: string) {
  const bin = atob(b64)
  const bytes = new Uint8Array(bin.length)
  for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i)
  const url = URL.createObjectURL(new Blob([bytes]))
  const a = document.createElement('a')
  a.href = url
  a.download = decodeURIComponent(filename)
  a.click()
  URL.revokeObjectURL(url)
}

async function onExportSubmit(payload: Record<string, unknown>) {
  try {
    const ids = payload.customer_ids as number[] | undefined
    const res = await exportFaults({
      columns: payload.columns,
      customer_id: ids?.length ? ids[0] : undefined,
      date_from: payload.date_from || undefined,
      date_to: payload.date_to || undefined,
    })
    saveBase64(res.content, res.filename)
    ui.toast('导出成功', 'success')
    exportVisible.value = false
  } catch (e) {
    ui.toast((e as Error).message, 'error')
  }
}

/** 客户下拉：优先按直接关联客户过滤；无直接关联时按负责区域过滤；再兜底全部 */
const regionCustomers = computed(() => {
  const custs = dicts.value?.customers || []
  const cids = user.user?.customer_ids || []
  if (cids.length) return custs.filter((c) => cids.includes(c.id))
  const rids = user.user?.region_ids || []
  if (!rids.length) return custs
  const filtered = custs.filter((c) => c.region_id !== null && rids.includes(c.region_id))
  return filtered.length ? filtered : custs
})

const query = reactive<Record<string, unknown>>({ search: '', fault_type: '', result: '' })
const tableRef = ref()

const columns = computed<DataColumn[]>(() => [
  { key: 'title', label: '标题', type: 'link', minWidth: 200, asTitle: true,
    link: (r) => `/app/faults/${r.id}` },
  { key: 'customer_name', label: '客户', minWidth: 100 },
  { key: 'handler', label: '处理人', width: 90 },
  { key: 'fault_time', label: '故障时间', width: 130 },
  { key: 'fault_type', label: '故障类型', width: 100 },
  { key: 'result', label: '处理结果', width: 90, type: 'tag', asTag: true, tagMap: FAULT_RESULT_TAG },
  { key: 'impact_range', label: '影响范围', minWidth: 120 },
  { key: 'actions', label: '操作', width: 140, type: 'action', fixed: 'right',
    actions: [
      { label: '查看', type: 'primary', link: true, perm: 'fault:view', icon: 'View',
        onClick: (row) => tableRef.value?.toggleExpand(row) },
      { label: '编辑', type: 'primary', link: true, perm: 'fault:edit', icon: 'Edit',
        onClick: (row) => openEdit(row as unknown as Fault) },
      { label: '删除', type: 'danger', link: true, perm: 'fault:delete', icon: 'Delete',
        onClick: (row) => onDelete(row as unknown as Fault) },
      { label: '转工单', type: 'warning', link: true, perm: 'ticket:add',
        disabled: (row: { ticket_id?: number | null }) => Boolean(row.ticket_id),
        onClick: (row) => onConvert(row as unknown as Fault) },
    ] },
])

async function onDelete(f: Fault) {
  try {
    await ElMessageBox.confirm(`确定删除故障「${f.title}」吗？`, '删除确认', { type: 'warning' })
  } catch { return }
  try {
    await deleteFault(f.id)
    ui.toast('已删除', 'success')
    tableRef.value?.refresh()
  } catch (e) {
    ui.toast((e as Error).message, 'error')
  }
}

async function onConvert(f: Fault) {
  try {
    await ElMessageBox.confirm(
      f.ticket_id ? `该故障已转工单 #${f.ticket_number || ''}，是否查看？`
                  : `确定将故障「${f.title}」转为工单吗？`, '转工单确认', { type: 'info' })
  } catch { return }
  try {
    if (f.ticket_id) {
      // 已转单 → 跳转工单
      const num = f.ticket_number || ''
      const res = await fetch('/api/tickets?search=' + encodeURIComponent(num)).then(r => r.json())
      const hit = res?.data?.items?.[0]
      if (hit?.id) { window.open(`/app/tickets/${hit.id}`, '_blank'); return }
      ui.toast('工单不存在或已被删除，可重新转单', 'warning')
    }
    const d = await convertFaultToTicket(f.id)
    ui.toast(`已转为工单 #${d.ticket_number}`, 'success')
    tableRef.value?.refresh()
  } catch (e) {
    ui.toast((e as Error).message, 'error')
  }
}

// 新建/编辑
const formVisible = ref(false)
const saving = ref(false)
const formRef = ref()
const form = reactive<Record<string, unknown>>({
  id: null, title: '', customer_id: null, handler: '', fault_time: '',
  fault_type: '', result: '已解决', recovery_time: '',
  fault_description: '', fault_cause: '', solution: '', impact_range: '',
})
const formRules = { title: [{ required: true, message: '请输入故障标题', trigger: 'blur' }] }

function blankForm() {
  return { id: null, title: '', customer_id: null, handler: '', fault_time: '',
    fault_type: '', result: '已解决', recovery_time: '',
    fault_description: '', fault_cause: '', solution: '', impact_range: '' }
}

function openCreate() {
  Object.assign(form, blankForm())
  // 驻场工程师：默认选中负责区域的第一个客户（无负责区域用户不受影响）
  const first = regionCustomers.value[0]
  if (first && !form.customer_id) form.customer_id = first.id
  formVisible.value = true
}

async function openEdit(f: Fault) {
  try {
    const detailData = await fetchFault(f.id)
    Object.assign(form, {
      id: detailData.id, title: detailData.title, customer_id: detailData.customer_id,
      handler: detailData.handler, fault_time: detailData.fault_time,
      fault_type: detailData.fault_type, result: detailData.result,
      recovery_time: detailData.recovery_time || '',
      fault_description: detailData.fault_description || '',
      fault_cause: detailData.fault_cause || '',
      solution: detailData.solution || '',
      impact_range: detailData.impact_range || '',
    })
    formVisible.value = true
  } catch { /* toast */ }
}

async function save() {
  try { await formRef.value?.validate() } catch { return }
  saving.value = true
  try {
    if (form.id) {
      await updateFault(form.id as number, { ...form })
      ui.toast('已保存', 'success')
    } else {
      await createFault({ ...form })
      ui.toast('故障记录已创建', 'success')
    }
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
  fetchFaultDicts().then((d) => (dicts.value = d))
})
</script>

<style scoped>
.filter-card { margin-bottom: 12px; }
.filter-row { display: flex; gap: 8px; flex-wrap: wrap; align-items: center; }
.filter-search { width: 200px; max-width: 100%; }
.filter-item { width: 130px; max-width: 100%; }
.header-actions { display: flex; gap: 8px; flex-wrap: wrap; }
.w-full { width: 100%; }
</style>
