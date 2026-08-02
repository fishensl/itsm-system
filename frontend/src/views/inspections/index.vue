<template>
  <div class="page-container">
    <div class="page-header">
      <h2 class="page-title">巡检记录</h2>
      <div class="header-actions">
        <el-button v-if="user.hasPerm('inspection:add')" type="primary" :icon="Plus" @click="openCreate">
          新建巡检
        </el-button>
      </div>
    </div>

    <!-- 筛选 -->
    <el-card shadow="never" class="filter-card">
      <div class="filter-row">
        <el-input v-model="query.search" placeholder="搜索标题" clearable class="filter-search"
          @keyup.enter="reload" @clear="reload" />
        <el-select v-model="query.status" placeholder="总体状态" clearable class="filter-item" @change="reload">
          <el-option v-for="s in dicts?.overall_statuses || []" :key="s" :label="s" :value="s" />
        </el-select>
        <el-select v-model="query.review_status" placeholder="审核状态" clearable class="filter-item" @change="reload">
          <el-option v-for="s in dicts?.review_statuses || []" :key="s" :label="s" :value="s" />
        </el-select>
        <el-select v-model="query.customer_id" placeholder="客户" clearable filterable class="filter-item" @change="reload">
          <el-option v-for="c in dicts?.customers || []" :key="c.id" :label="c.name" :value="c.id" />
        </el-select>
        <el-button type="primary" plain :icon="Search" @click="reload">查询</el-button>
      </div>
    </el-card>

    <!-- 列表 -->
    <DataTable
      ref="tableRef"
      :columns="columns"
      :fetch-data="fetchInspections"
      :query="query"
      row-key="id"
      @row-click="openDetail"
    />

    <!-- 详情抽屉 -->
    <el-drawer v-model="detailVisible" :title="detail ? `#${detail.id} · ${detail.title}` : ''"
      size="560px" destroy-on-close>
      <div v-if="detail">
        <el-descriptions :column="2" border size="small">
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
          <el-descriptions-item label="巡检日期">{{ detail.inspection_date || '-' }}</el-descriptions-item>
          <el-descriptions-item label="巡检人员">{{ detail.inspector_name || '-' }}</el-descriptions-item>
          <el-descriptions-item label="报告">{{ detail.report_label }}</el-descriptions-item>
          <el-descriptions-item label="巡检地点">{{ detail.location || '-' }}</el-descriptions-item>
          <el-descriptions-item label="创建时间">{{ detail.created_at }}</el-descriptions-item>
        </el-descriptions>

        <el-divider content-position="left">结论</el-divider>
        <p class="detail-text">{{ detail.conclusion || '-' }}</p>

        <template v-if="detail.review_comment">
          <el-divider content-position="left">审核意见</el-divider>
          <p class="detail-text">{{ detail.review_comment }}</p>
        </template>

        <!-- 审核操作 -->
        <el-divider content-position="left">操作</el-divider>
        <div class="action-bar">
          <template v-if="detail.review_status === '草稿'">
            <el-button v-if="user.hasPerm('inspection:edit')" size="small" type="primary"
              @click="onSubmit">提交审核</el-button>
          </template>
          <template v-else-if="detail.review_status === '待审核'">
            <el-button v-if="user.hasPerm('inspection:review')" size="small" type="success"
              @click="onReview(true)">审核通过</el-button>
            <el-button v-if="user.hasPerm('inspection:review')" size="small" type="danger"
              @click="onReview(false)">退回</el-button>
          </template>
          <el-button v-if="user.hasPerm('inspection:edit')" size="small" type="primary" plain
            @click="openEdit(detail)">编辑</el-button>
          <el-button v-if="user.hasPerm('inspection:delete')" size="small" type="danger" plain
            @click="onDelete(detail)">删除</el-button>
        </div>
      </div>
    </el-drawer>

    <!-- 新建/编辑巡检 -->
    <el-dialog v-model="formVisible" :title="form.id ? '编辑巡检' : '新建巡检'" width="600px" top="5vh"
      destroy-on-close>
      <el-form ref="formRef" :model="form" :rules="formRules" label-width="90px">
        <el-form-item label="标题" prop="title">
          <el-input v-model="form.title" placeholder="必填，如：核心机房月度巡检" />
        </el-form-item>
        <el-row :gutter="12">
          <el-col :xs="24" :sm="12">
            <el-form-item label="客户" prop="customer_id">
              <el-select v-model="form.customer_id" filterable clearable class="w-full" placeholder="必选">
                <el-option v-for="c in dicts?.customers || []" :key="c.id" :label="c.name" :value="c.id" />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :xs="24" :sm="12">
            <el-form-item label="巡检日期">
              <el-date-picker v-model="form.inspection_date" type="date" value-format="YYYY-MM-DD"
                class="w-full" placeholder="巡检日期" />
            </el-form-item>
          </el-col>
          <el-col :xs="24" :sm="12">
            <el-form-item label="巡检人员">
              <el-select v-model="form.inspector_user_id" filterable clearable class="w-full" placeholder="巡检人员">
                <el-option v-for="p in dicts?.inspectors || []" :key="p.user_id" :label="p.name" :value="p.user_id" />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :xs="24" :sm="12">
            <el-form-item label="总体状态">
              <el-select v-model="form.overall_status" class="w-full">
                <el-option v-for="s in dicts?.overall_statuses || []" :key="s" :label="s" :value="s" />
              </el-select>
            </el-form-item>
          </el-col>
        </el-row>
        <el-form-item label="结论">
          <el-input v-model="form.conclusion" type="textarea" :rows="3" placeholder="巡检结论（可选）" />
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
import { ref, reactive, computed, onMounted } from 'vue'
import { ElMessageBox } from 'element-plus'
import { Plus, Search } from '@element-plus/icons-vue'
import DataTable, { type DataColumn } from '@/components/DataTable.vue'
import { useUserStore } from '@/stores/user'
import { useUiStore } from '@/stores/ui'
import {
  fetchInspections, fetchInspection, createInspection, updateInspection, deleteInspection,
  submitInspection, reviewInspection, fetchInspectionDicts,
  OVERALL_STATUS_TAG, REVIEW_STATUS_TAG, type Inspection, type InspectionDicts,
} from '@/api/inspections'

const user = useUserStore()
const ui = useUiStore()
const dicts = ref<InspectionDicts | null>(null)

const query = reactive<Record<string, unknown>>({
  search: '', status: '', review_status: '', customer_id: undefined,
})
const tableRef = ref()

const columns = computed<DataColumn[]>(() => [
  { key: 'title', label: '标题', type: 'link', minWidth: 180, asTitle: true,
    link: (r) => `/app/inspections/${r.id}` },
  { key: 'customer_name', label: '客户', minWidth: 100 },
  { key: 'inspection_date', label: '巡检日期', width: 100 },
  { key: 'inspector_name', label: '巡检人员', width: 90 },
  { key: 'overall_status', label: '总体状态', width: 90, type: 'tag', asTag: true,
    tagMap: OVERALL_STATUS_TAG },
  { key: 'review_status', label: '审核状态', width: 90, type: 'tag', tagMap: REVIEW_STATUS_TAG },
  { key: 'report_label', label: '报告', width: 70 },
  { key: 'actions', label: '操作', width: 150, type: 'action', fixed: 'right',
    actions: [
      { label: '查看', type: 'primary', link: true, perm: 'inspection:view', icon: 'View',
        onClick: (row) => openDetail(row) },
      { label: '编辑', type: 'primary', link: true, perm: 'inspection:edit', icon: 'Edit',
        onClick: (row) => openEdit(row as unknown as Inspection) },
      { label: '删除', type: 'danger', link: true, perm: 'inspection:delete', icon: 'Delete',
        onClick: (row) => onDelete(row as unknown as Inspection) },
    ] },
])

// 详情
const detailVisible = ref(false)
const detail = ref<Inspection | null>(null)

async function openDetail(row: Record<string, unknown>) {
  try {
    detail.value = await fetchInspection(row.id as number)
    detailVisible.value = true
  } catch { /* toast */ }
}

async function refreshDetail() {
  if (!detail.value) return
  try {
    detail.value = await fetchInspection(detail.value.id)
  } catch { /* toast */ }
}

async function onSubmit() {
  if (!detail.value) return
  try {
    await submitInspection(detail.value.id)
    ui.toast('已提交审核', 'success')
    await refreshDetail()
    tableRef.value?.refresh()
  } catch (e) {
    ui.toast((e as Error).message, 'error')
  }
}

function onReview(approved: boolean) {
  if (!detail.value) return
  const action = approved ? '审核通过' : '退回'
  ElMessageBox.prompt(`${action}该巡检？可填写审核意见`, action, {
    inputType: 'textarea',
    inputPlaceholder: approved ? '审核意见（可选）' : '退回原因（可选）',
    confirmButtonText: action,
  }).then(async ({ value }) => {
    if (!detail.value) return
    try {
      await reviewInspection(detail.value.id, approved, (value || '').trim())
      ui.toast(`${action}成功`, 'success')
      await refreshDetail()
      tableRef.value?.refresh()
    } catch (e) {
      ui.toast((e as Error).message, 'error')
    }
  }).catch(() => {})
}

async function onDelete(i: Inspection) {
  try {
    await ElMessageBox.confirm(`确定删除巡检「${i.title}」吗？`, '删除确认', { type: 'warning' })
  } catch { return }
  try {
    await deleteInspection(i.id)
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
  id: null, title: '', customer_id: null, inspection_date: '', inspector_user_id: null,
  overall_status: '正常', conclusion: '',
})
const formRules = {
  title: [{ required: true, message: '请输入巡检标题', trigger: 'blur' }],
  customer_id: [{ required: true, message: '请选择客户', trigger: 'change' }],
}

function blankForm() {
  return { id: null, title: '', customer_id: null, inspection_date: '', inspector_user_id: null,
    overall_status: '正常', conclusion: '' }
}

function openCreate() {
  Object.assign(form, blankForm())
  formVisible.value = true
}

function openEdit(i: Inspection) {
  Object.assign(form, {
    id: i.id, title: i.title, customer_id: i.customer_id,
    inspection_date: i.inspection_date || '', overall_status: i.overall_status,
    conclusion: i.conclusion || '', inspector_user_id: null,
  })
  formVisible.value = true
}

async function save() {
  try { await formRef.value?.validate() } catch { return }
  saving.value = true
  try {
    if (form.id) {
      await updateInspection(form.id as number, { ...form })
      ui.toast('已保存', 'success')
    } else {
      await createInspection({ ...form })
      ui.toast('巡检记录已创建', 'success')
    }
    formVisible.value = false
    await refreshDetail()
    tableRef.value?.refresh()
  } catch (e) {
    ui.toast((e as Error).message, 'error')
  } finally {
    saving.value = false
  }
}

function reload() { tableRef.value?.refresh() }

onMounted(() => {
  fetchInspectionDicts().then((d) => (dicts.value = d))
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
