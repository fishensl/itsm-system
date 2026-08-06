<template>
  <div class="page-container">
    <div class="page-header">
      <h2 class="page-title">故障记录</h2>
      <div class="header-actions">
        <el-button v-if="user.hasPerm('fault:add')" type="primary" :icon="Plus" @click="openCreate">
          新建故障
        </el-button>
      </div>
    </div>

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

    <!-- 列表 -->
    <DataTable
      ref="tableRef"
      :columns="columns"
      :fetch-data="fetchFaults"
      :query="query"
      row-key="id"
      @row-click="openDetail"
    />

    <!-- 详情抽屉 -->
    <el-drawer v-model="detailVisible" :title="detail ? `#${detail.id} · ${detail.title}` : ''"
      size="620px" destroy-on-close>
      <div v-if="detail">
        <el-descriptions :column="2" border size="small">
          <el-descriptions-item label="客户">{{ detail.customer_name || '-' }}</el-descriptions-item>
          <el-descriptions-item label="故障时间">{{ detail.fault_time || '-' }}</el-descriptions-item>
          <el-descriptions-item label="处理人">{{ detail.handler || '-' }}</el-descriptions-item>
          <el-descriptions-item label="故障类型">{{ detail.fault_type || '-' }}</el-descriptions-item>
          <el-descriptions-item label="处理结果">
            <el-tag size="small" :type="FAULT_RESULT_TAG[detail.result] || 'danger'">
              {{ detail.result || '-' }}
            </el-tag>
          </el-descriptions-item>
          <el-descriptions-item label="恢复时间">{{ detail.recovery_time || '-' }}</el-descriptions-item>
        </el-descriptions>

        <el-divider content-position="left">故障描述</el-divider>
        <p class="detail-text">{{ detail.fault_description || '-' }}</p>

        <el-divider content-position="left">故障原因</el-divider>
        <p class="detail-text">{{ detail.fault_cause || '-' }}</p>

        <el-divider content-position="left">解决方案</el-divider>
        <p class="detail-text">{{ detail.solution || '-' }}</p>

        <el-divider content-position="left">影响范围</el-divider>
        <p class="detail-text">{{ detail.impact_range || '-' }}</p>

        <!-- 操作 -->
        <el-divider content-position="left">操作</el-divider>
        <div class="action-bar">
          <el-button v-if="user.hasPerm('fault:edit')" size="small" type="primary" plain
            @click="openEdit(detail)">编辑</el-button>
          <el-button v-if="user.hasPerm('fault:delete')" size="small" type="danger" plain
            @click="onDelete(detail)">删除</el-button>
        </div>
      </div>
    </el-drawer>

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
import { Plus, Search } from '@element-plus/icons-vue'
import DataTable, { type DataColumn } from '@/components/DataTable.vue'
import { useUserStore } from '@/stores/user'
import { useUiStore } from '@/stores/ui'
import {
  fetchFaults, fetchFault, createFault, updateFault, deleteFault,
  fetchFaultDicts, FAULT_RESULT_TAG, type Fault, type FaultDicts,
} from '@/api/faults'

const user = useUserStore()
const ui = useUiStore()
const dicts = ref<FaultDicts | null>(null)

/** 客户下拉：驻场工程师（配置了负责区域）仅显示对应区域客户；区域无客户时兜底全部 */
const regionCustomers = computed(() => {
  const custs = dicts.value?.customers || []
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
        onClick: (row) => openDetail(row) },
      { label: '编辑', type: 'primary', link: true, perm: 'fault:edit', icon: 'Edit',
        onClick: (row) => openEdit(row as unknown as Fault) },
      { label: '删除', type: 'danger', link: true, perm: 'fault:delete', icon: 'Delete',
        onClick: (row) => onDelete(row as unknown as Fault) },
    ] },
])

// 详情
const detailVisible = ref(false)
const detail = ref<Fault | null>(null)

async function openDetail(row: Record<string, unknown>) {
  try {
    detail.value = await fetchFault(row.id as number)
    detailVisible.value = true
  } catch { /* toast */ }
}

async function onDelete(f: Fault) {
  try {
    await ElMessageBox.confirm(`确定删除故障「${f.title}」吗？`, '删除确认', { type: 'warning' })
  } catch { return }
  try {
    await deleteFault(f.id)
    ui.toast('已删除', 'success')
    detailVisible.value = false
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
.detail-text { white-space: pre-wrap; word-break: break-all; font-size: 13px; }
.action-bar { display: flex; gap: 8px; flex-wrap: wrap; align-items: center; }
</style>
