<template>
  <div class="page-container">
    <div class="page-header">
      <h2 class="page-title">销售管线</h2>
    </div>

    <el-card shadow="never" class="tabs-card">
      <el-tabs v-model="activeTab" class="module-tabs">
        <!-- ==================== 商机 ==================== -->
        <el-tab-pane label="商机跟进" name="opps" lazy>
          <div class="tab-toolbar">
            <div class="filter-row">
              <el-input v-model="oppQuery.search" placeholder="搜索商机标题" clearable class="filter-search"
                @keyup.enter="reload('opp')" @clear="reload('opp')" />
              <el-select v-model="oppQuery.stage" placeholder="阶段" clearable class="filter-item"
                @change="reload('opp')">
                <el-option v-for="s in dicts?.opp_stages || []" :key="s" :label="s" :value="s" />
              </el-select>
              <el-button type="primary" plain :icon="Search" @click="reload('opp')">查询</el-button>
            </div>
            <el-button v-if="user.hasPerm('sales:add')" type="primary" :icon="Plus" @click="openOppCreate">
              新增商机
            </el-button>
          </div>

          <DataTable ref="oppTableRef" :columns="oppColumns" :fetch-data="fetchOpportunities" :column-settings="{ storageKey: 'cols_sales_opps' }"
            :query="oppQuery" row-key="id" />

          <el-dialog v-model="oppFormVisible" :title="oppForm.id ? '编辑商机' : '新增商机'" width="620px" top="5vh"
            destroy-on-close>
            <el-form ref="oppFormRef" :model="oppForm" :rules="oppFormRules" label-width="110px">
              <el-form-item label="商机标题" prop="title">
                <el-input v-model="oppForm.title" placeholder="必填" />
              </el-form-item>
              <el-row :gutter="12">
                <el-col :xs="24" :sm="12">
                  <el-form-item label="客户">
                    <el-select v-model="oppForm.customer_id" filterable clearable class="w-full">
                      <el-option v-for="c in dicts?.customers || []" :key="c.id" :label="c.name" :value="c.id" />
                    </el-select>
                  </el-form-item>
                </el-col>
                <el-col :xs="24" :sm="12">
                  <el-form-item label="阶段">
                    <el-select v-model="oppForm.stage" class="w-full">
                      <el-option v-for="s in dicts?.opp_stages || []" :key="s" :label="s" :value="s" />
                    </el-select>
                  </el-form-item>
                </el-col>
                <el-col :xs="24" :sm="12">
                  <el-form-item label="预计金额">
                    <el-input-number v-model="oppForm.expected_amount" :min="0" :precision="2" class="w-full" />
                  </el-form-item>
                </el-col>
                <el-col :xs="24" :sm="12">
                  <el-form-item label="预计成交日">
                    <el-date-picker v-model="oppForm.expected_close_date" type="date" value-format="YYYY-MM-DD"
                      class="w-full" />
                  </el-form-item>
                </el-col>
                <el-col :xs="24" :sm="12">
                  <el-form-item label="负责人">
                    <el-input v-model="oppForm.owner" placeholder="默认当前用户" />
                  </el-form-item>
                </el-col>
              </el-row>
              <el-form-item label="备注">
                <el-input v-model="oppForm.remark" type="textarea" :rows="2" />
              </el-form-item>
            </el-form>
            <template #footer>
              <el-button @click="oppFormVisible = false">取消</el-button>
              <el-button type="primary" :loading="saving" @click="saveOpp">保存</el-button>
            </template>
          </el-dialog>
        </el-tab-pane>

        <!-- ==================== 报价 ==================== -->
        <el-tab-pane label="报价单" name="quotations" lazy>
          <div class="tab-toolbar">
            <div class="filter-row">
              <el-input v-model="quotQuery.search" placeholder="搜索报价单号" clearable class="filter-search"
                @keyup.enter="reload('quot')" @clear="reload('quot')" />
              <el-select v-model="quotQuery.status" placeholder="状态" clearable class="filter-item"
                @change="reload('quot')">
                <el-option v-for="s in dicts?.quotation_statuses || []" :key="s" :label="s" :value="s" />
              </el-select>
              <el-button type="primary" plain :icon="Search" @click="reload('quot')">查询</el-button>
            </div>
            <el-button v-if="user.hasPerm('sales:add')" type="primary" :icon="Plus" @click="openQuotCreate">
              新增报价单
            </el-button>
          </div>

          <DataTable ref="quotTableRef" :columns="quotColumns" :fetch-data="fetchQuotations" :column-settings="{ storageKey: 'cols_sales_quot' }"
            :query="quotQuery" row-key="id" />

          <el-dialog v-model="quotFormVisible" :title="quotForm.id ? '编辑报价单' : '新增报价单'" width="600px" top="5vh"
            destroy-on-close>
            <el-form ref="quotFormRef" :model="quotForm" label-width="110px">
              <el-row :gutter="12">
                <el-col :xs="24" :sm="12">
                  <el-form-item label="报价单号">
                    <el-input v-model="quotForm.number" />
                  </el-form-item>
                </el-col>
                <el-col :xs="24" :sm="12">
                  <el-form-item label="关联商机">
                    <el-select v-model="quotForm.opportunity_id" filterable clearable class="w-full">
                      <el-option v-for="o in dicts?.opportunities || []" :key="o.id" :label="o.title"
                        :value="o.id" />
                    </el-select>
                  </el-form-item>
                </el-col>
                <el-col :xs="24" :sm="12">
                  <el-form-item label="客户" prop="customer_id" :rules="{ required: true, message: '请选择客户', trigger: 'change' }">
                    <el-select v-model="quotForm.customer_id" filterable clearable class="w-full">
                      <el-option v-for="c in dicts?.customers || []" :key="c.id" :label="c.name" :value="c.id" />
                    </el-select>
                  </el-form-item>
                </el-col>
                <el-col :xs="24" :sm="12">
                  <el-form-item label="总金额" prop="total_amount" :rules="{ required: true, message: '请输入总金额', trigger: 'change' }">
                    <el-input-number v-model="quotForm.total_amount" :min="0" :precision="2" class="w-full" />
                  </el-form-item>
                </el-col>
                <el-col :xs="24" :sm="12">
                  <el-form-item label="状态">
                    <el-select v-model="quotForm.status" class="w-full">
                      <el-option v-for="s in dicts?.quotation_statuses || []" :key="s" :label="s" :value="s" />
                    </el-select>
                  </el-form-item>
                </el-col>
                <el-col :xs="24" :sm="12">
                  <el-form-item label="有效期至">
                    <el-date-picker v-model="quotForm.valid_until" type="date" value-format="YYYY-MM-DD"
                      class="w-full" />
                  </el-form-item>
                </el-col>
              </el-row>
              <!-- 报价明细行（联动总金额） -->
              <el-form-item label="报价明细">
                <div class="quot-items">
                  <div v-for="(it, idx) in quotForm.items" :key="idx" class="quot-item-row">
                    <el-input v-model="it.name" placeholder="品名" size="small" style="flex: 2" />
                    <el-input-number v-model="it.quantity" :min="0" size="small" style="width: 110px" />
                    <el-input-number v-model="it.unit_price" :min="0" :precision="2" size="small"
                      style="width: 130px" />
                    <span class="quot-item-amount">¥{{ fmtMoney(it.quantity * it.unit_price) }}</span>
                    <el-button size="small" text type="danger" :icon="Delete" @click="removeQuotItem(idx)" />
                  </div>
                  <el-button size="small" plain :icon="Plus" @click="addQuotItem">添加明细行</el-button>
                  <div class="quot-item-total">合计：¥{{ fmtMoney(quotItemsTotal) }}</div>
                </div>
              </el-form-item>
            </el-form>
            <template #footer>
              <el-button @click="quotFormVisible = false">取消</el-button>
              <el-button type="primary" :loading="saving" @click="saveQuot">保存</el-button>
            </template>
          </el-dialog>
        </el-tab-pane>

        <!-- ==================== 合同 ==================== -->
        <el-tab-pane label="合同管理" name="contracts" lazy>
          <div class="tab-toolbar">
            <div class="filter-row">
              <el-input v-model="contractQuery.search" placeholder="搜索标题 / 编号" clearable class="filter-search"
                @keyup.enter="reload('contract')" @clear="reload('contract')" />
              <el-select v-model="contractQuery.status" placeholder="状态" clearable class="filter-item"
                @change="reload('contract')">
                <el-option v-for="s in dicts?.contract_statuses || []" :key="s" :label="s" :value="s" />
              </el-select>
              <el-button type="primary" plain :icon="Search" @click="reload('contract')">查询</el-button>
            </div>
            <el-button v-if="user.hasPerm('sales:add')" type="primary" :icon="Plus" @click="openContractCreate">
              新增合同
            </el-button>
          </div>

          <DataTable ref="contractTableRef" :columns="contractColumns" :fetch-data="fetchContracts" :column-settings="{ storageKey: 'cols_sales_contracts' }"
            :query="contractQuery" row-key="id" />

          <el-dialog v-model="contractFormVisible" :title="contractForm.id ? '编辑合同' : '新增合同'" width="680px"
            top="5vh" destroy-on-close>
            <el-form ref="contractFormRef" :model="contractForm" :rules="contractFormRules" label-width="110px">
              <el-row :gutter="12">
                <el-col :xs="24" :sm="12">
                  <el-form-item label="合同编号">
                    <el-input v-model="contractForm.number" />
                  </el-form-item>
                </el-col>
                <el-col :xs="24" :sm="12">
                  <el-form-item label="合同标题" prop="title">
                    <el-input v-model="contractForm.title" placeholder="必填" />
                  </el-form-item>
                </el-col>
                <el-col :xs="24" :sm="12">
                  <el-form-item label="客户">
                    <el-select v-model="contractForm.customer_id" filterable clearable class="w-full">
                      <el-option v-for="c in dicts?.customers || []" :key="c.id" :label="c.name" :value="c.id" />
                    </el-select>
                  </el-form-item>
                </el-col>
                <el-col :xs="24" :sm="12">
                  <el-form-item label="合同金额">
                    <el-input-number v-model="contractForm.amount" :min="0" :precision="2" class="w-full" />
                  </el-form-item>
                </el-col>
                <el-col :xs="24" :sm="12">
                  <el-form-item label="状态">
                    <el-select v-model="contractForm.status" class="w-full">
                      <el-option v-for="s in dicts?.contract_statuses || []" :key="s" :label="s" :value="s" />
                    </el-select>
                  </el-form-item>
                </el-col>
                <el-col :xs="24" :sm="12">
                  <el-form-item label="开始日期">
                    <el-date-picker v-model="contractForm.start_date" type="date" value-format="YYYY-MM-DD"
                      class="w-full" />
                  </el-form-item>
                </el-col>
                <el-col :xs="24" :sm="12">
                  <el-form-item label="结束日期">
                    <el-date-picker v-model="contractForm.end_date" type="date" value-format="YYYY-MM-DD"
                      class="w-full" />
                  </el-form-item>
                </el-col>
                <el-col :xs="24" :sm="12">
                  <el-form-item label="巡检频率">
                    <el-select v-model="contractForm.inspection_frequency" clearable class="w-full">
                      <el-option v-for="f in dicts?.frequencies || []" :key="f" :label="f" :value="f" />
                    </el-select>
                  </el-form-item>
                </el-col>
                <el-col :xs="24" :sm="12">
                  <el-form-item label="巡检模板">
                    <el-select v-model="contractForm.task_template_id" filterable clearable class="w-full">
                      <el-option v-for="t in dicts?.templates || []" :key="t.id" :label="t.name" :value="t.id" />
                    </el-select>
                  </el-form-item>
                </el-col>
                <el-col :xs="24">
                  <el-form-item label="自动生成">
                    <el-checkbox v-model="contractForm.auto_generate_tasks">
                      按巡检频率自动生成巡检任务
                    </el-checkbox>
                  </el-form-item>
                </el-col>
              </el-row>
            </el-form>
            <template #footer>
              <el-button @click="contractFormVisible = false">取消</el-button>
              <el-button type="primary" :loading="saving" @click="saveContract">保存</el-button>
            </template>
          </el-dialog>
        </el-tab-pane>

        <!-- ==================== 项目 ==================== -->
        <el-tab-pane label="项目管理" name="projects" lazy>
          <div class="tab-toolbar">
            <div class="filter-row">
              <el-input v-model="projectQuery.search" placeholder="搜索项目名称" clearable class="filter-search"
                @keyup.enter="reload('project')" @clear="reload('project')" />
              <el-select v-model="projectQuery.status" placeholder="状态" clearable class="filter-item"
                @change="reload('project')">
                <el-option v-for="s in dicts?.project_statuses || []" :key="s" :label="s" :value="s" />
              </el-select>
              <el-button type="primary" plain :icon="Search" @click="reload('project')">查询</el-button>
            </div>
            <el-button v-if="user.hasPerm('sales:add')" type="primary" :icon="Plus" @click="openProjectCreate">
              新增项目
            </el-button>
          </div>

          <DataTable ref="projectTableRef" :columns="projectColumns" :fetch-data="fetchProjects" :column-settings="{ storageKey: 'cols_sales_projects' }"
            :query="projectQuery" row-key="id" />

          <el-dialog v-model="projectFormVisible" :title="projectForm.id ? '编辑项目' : '新增项目'" width="640px"
            top="5vh" destroy-on-close>
            <el-form ref="projectFormRef" :model="projectForm" :rules="projectFormRules" label-width="110px">
              <el-row :gutter="12">
                <el-col :xs="24" :sm="12">
                  <el-form-item label="项目名称" prop="name">
                    <el-input v-model="projectForm.name" placeholder="必填" />
                  </el-form-item>
                </el-col>
                <el-col :xs="24" :sm="12">
                  <el-form-item label="关联合同">
                    <el-select v-model="projectForm.contract_id" filterable clearable class="w-full">
                      <el-option v-for="ct in dicts?.contracts || []" :key="ct.id" :label="ct.title"
                        :value="ct.id" />
                    </el-select>
                  </el-form-item>
                </el-col>
                <el-col :xs="24" :sm="12">
                  <el-form-item label="客户">
                    <el-select v-model="projectForm.customer_id" filterable clearable class="w-full">
                      <el-option v-for="c in dicts?.customers || []" :key="c.id" :label="c.name" :value="c.id" />
                    </el-select>
                  </el-form-item>
                </el-col>
                <el-col :xs="24" :sm="12">
                  <el-form-item label="负责人">
                    <el-input v-model="projectForm.manager" placeholder="默认当前用户" />
                  </el-form-item>
                </el-col>
                <el-col :xs="24" :sm="12">
                  <el-form-item label="状态">
                    <el-select v-model="projectForm.status" class="w-full">
                      <el-option v-for="s in dicts?.project_statuses || []" :key="s" :label="s" :value="s" />
                    </el-select>
                  </el-form-item>
                </el-col>
                <el-col :xs="24" :sm="12">
                  <el-form-item label="进度(%)">
                    <el-input-number v-model="projectForm.progress" :min="0" :max="100" class="w-full" />
                  </el-form-item>
                </el-col>
                <el-col :xs="24" :sm="12">
                  <el-form-item label="预算">
                    <el-input-number v-model="projectForm.budget" :min="0" :precision="2" class="w-full" />
                  </el-form-item>
                </el-col>
                <el-col :xs="24" :sm="12">
                  <el-form-item label="开始日期">
                    <el-date-picker v-model="projectForm.start_date" type="date" value-format="YYYY-MM-DD"
                      class="w-full" />
                  </el-form-item>
                </el-col>
                <el-col :xs="24" :sm="12">
                  <el-form-item label="结束日期">
                    <el-date-picker v-model="projectForm.end_date" type="date" value-format="YYYY-MM-DD"
                      class="w-full" />
                  </el-form-item>
                </el-col>
              </el-row>
            </el-form>
            <template #footer>
              <el-button @click="projectFormVisible = false">取消</el-button>
              <el-button type="primary" :loading="saving" @click="saveProject">保存</el-button>
            </template>
          </el-dialog>
        </el-tab-pane>
      </el-tabs>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ElMessageBox } from 'element-plus/es/components/message-box/index'
import { ref, reactive, computed, onMounted, watch } from 'vue'
import { useRoute } from 'vue-router'
import { Plus, Search, Delete } from '@element-plus/icons-vue'
import DataTable, { type DataColumn } from '@/components/DataTable.vue'
import { fetchEntityMetas, mergeFieldMeta, type EntityFieldMeta } from '@/api/meta'
import { useUserStore } from '@/stores/user'
import { useUiStore } from '@/stores/ui'
import { BOOL_LABELS } from '@/utils/labels'
import {
  fetchOpportunities, createOpportunity, updateOpportunity, deleteOpportunity,
  fetchQuotations, createQuotation, updateQuotation, deleteQuotation,
  fetchContracts, createContract, updateContract, deleteContract,
  fetchProjects, createProject, updateProject, deleteProject,
  fetchSalesDicts, OPP_STAGE_TAG, QUOTATION_STATUS_TAG, CONTRACT_STATUS_TAG, PROJECT_STATUS_TAG,
  type Opportunity, type Quotation, type ContractItem, type ProjectItem, type SalesDicts,
} from '@/api/sales'

const user = useUserStore()
const ui = useUiStore()
const dicts = ref<SalesDicts | null>(null)
const fieldMeta = reactive<Record<string, EntityFieldMeta[]>>({})

const activeTab = ref('opps')
const oppTableRef = ref()
const quotTableRef = ref()
const contractTableRef = ref()
const projectTableRef = ref()

// 侧栏入口（/app/sales?tab=opps 等）自动定位标签页
const route = useRoute()
watch(
  () => route.query.tab,
  (tab) => {
    if (tab && ['opps', 'quotations', 'contracts', 'projects'].includes(String(tab))) {
      activeTab.value = String(tab)
    }
  },
  { immediate: true },
)

const oppQuery = reactive<Record<string, unknown>>({ search: '', stage: '' })
const quotQuery = reactive<Record<string, unknown>>({ search: '', status: '' })
const contractQuery = reactive<Record<string, unknown>>({ search: '', status: '' })
const projectQuery = reactive<Record<string, unknown>>({ search: '', status: '' })

function reload(kind: 'opp' | 'quot' | 'contract' | 'project') {
  const refs = { opp: oppTableRef, quot: quotTableRef, contract: contractTableRef, project: projectTableRef }
  refs[kind].value?.refresh()
}

// ==================== 商机 ====================
const oppColumns = computed<DataColumn[]>(() => mergeFieldMeta([
  { key: 'title', label: '商机标题', minWidth: 200, asTitle: true },
  { key: 'customer_name', label: '客户', minWidth: 120 },
  { key: 'stage', label: '阶段', width: 100, type: 'tag', asTag: true, tagMap: OPP_STAGE_TAG },
  { key: 'expected_amount', label: '预计金额', width: 110, type: 'money' },
  { key: 'expected_close_date', label: '预计成交日', width: 110, type: 'date' },
  { key: 'owner', label: '负责人', width: 90 },
  { key: 'actions', label: '操作', width: 110, type: 'action', fixed: 'right',
    actions: [
      { label: '编辑', type: 'primary', link: true, perm: 'sales:edit', icon: 'Edit',
        onClick: (row) => openOppEdit(row as unknown as Opportunity) },
      { label: '删除', type: 'danger', link: true, perm: 'sales:delete', icon: 'Delete',
        onClick: (row) => onOppDelete(row as unknown as Opportunity) },
    ] },
], fieldMeta.opportunity || []))

interface OppFormModel {
  id?: number
  title: string
  customer_id: number | null
  stage: string
  expected_amount: number
  expected_close_date: string
  owner: string
  remark: string
}

const oppFormVisible = ref(false)
const saving = ref(false)
const oppFormRef = ref()
const oppForm = reactive<OppFormModel>(blankOppForm())

function blankOppForm(): OppFormModel {
  return {
    id: undefined, title: '', customer_id: null, stage: '初步接触', expected_amount: 0,
    expected_close_date: '', owner: '', remark: '',
  }
}

const oppFormRules = { title: [{ required: true, message: '请输入商机标题', trigger: 'blur' }] }

function openOppCreate() {
  Object.assign(oppForm, blankOppForm())
  oppFormVisible.value = true
}

function openOppEdit(o: Opportunity) {
  Object.assign(oppForm, blankOppForm(), {
    id: o.id, title: o.title, customer_id: o.customer_id, stage: o.stage || '初步接触',
    expected_amount: o.expected_amount, expected_close_date: o.expected_close_date,
    owner: o.owner, remark: o.remark,
  })
  oppFormVisible.value = true
}

async function saveOpp() {
  try { await oppFormRef.value?.validate() } catch { return }
  saving.value = true
  try {
    if (oppForm.id) {
      await updateOpportunity(oppForm.id, { ...oppForm })
      ui.toast('商机已更新', 'success')
    } else {
      await createOpportunity({ ...oppForm })
      ui.toast('商机已创建', 'success')
    }
    oppFormVisible.value = false
    reload('opp')
  } catch (e) {
    ui.toast((e as Error).message, 'error')
  } finally {
    saving.value = false
  }
}

async function onOppDelete(o: Opportunity) {
  try {
    await ElMessageBox.confirm(`确定删除商机「${o.title}」吗？`, '删除确认', { type: 'warning' })
  } catch { return }
  try {
    await deleteOpportunity(o.id)
    ui.toast('已删除', 'success')
    reload('opp')
  } catch (e) {
    ui.toast((e as Error).message, 'error')
  }
}

// ==================== 报价 ====================
const quotColumns = computed<DataColumn[]>(() => mergeFieldMeta([
  { key: 'number', label: '报价单号', minWidth: 130, asTitle: true },
  { key: 'customer_name', label: '客户', minWidth: 120 },
  { key: 'opportunity_title', label: '关联商机', minWidth: 140 },
  { key: 'total_amount', label: '总金额', width: 110, type: 'money' },
  { key: 'status', label: '状态', width: 90, type: 'tag', asTag: true, tagMap: QUOTATION_STATUS_TAG },
  { key: 'valid_until', label: '有效期至', width: 110, type: 'date' },
  { key: 'actions', label: '操作', width: 110, type: 'action', fixed: 'right',
    actions: [
      { label: '编辑', type: 'primary', link: true, perm: 'sales:edit', icon: 'Edit',
        onClick: (row) => openQuotEdit(row as unknown as Quotation) },
      { label: '删除', type: 'danger', link: true, perm: 'sales:delete', icon: 'Delete',
        onClick: (row) => onQuotDelete(row as unknown as Quotation) },
    ] },
], fieldMeta.quotation || []))

interface QuotFormModel {
  id?: number
  number: string
  opportunity_id: number | null
  customer_id: number | null
  total_amount: number
  valid_until: string
  status: string
  items: Array<{ name: string; quantity: number; unit_price: number }>
}

const quotFormVisible = ref(false)
const quotFormRef = ref()
const quotForm = reactive<QuotFormModel>(blankQuotForm())

function blankQuotForm(): QuotFormModel {
  return {
    id: undefined, number: '', opportunity_id: null, customer_id: null,
    total_amount: 0, valid_until: '', status: '草稿', items: [],
  }
}

function fmtMoney(v: number) {
  return Number(v || 0).toLocaleString('zh-CN', { minimumFractionDigits: 0, maximumFractionDigits: 2 })
}

const quotItemsTotal = computed(() =>
  (quotForm.items || []).reduce((s, it) => s + (it.quantity || 0) * (it.unit_price || 0), 0))

function addQuotItem() {
  quotForm.items.push({ name: '', quantity: 1, unit_price: 0 })
}

function removeQuotItem(idx: number) {
  quotForm.items.splice(idx, 1)
}

function openQuotCreate() {
  Object.assign(quotForm, blankQuotForm(), { items: [] })
  quotFormVisible.value = true
}

function openQuotEdit(q: Quotation) {
  Object.assign(quotForm, blankQuotForm(), {
    id: q.id, number: q.number, opportunity_id: q.opportunity_id, customer_id: q.customer_id,
    total_amount: q.total_amount, valid_until: q.valid_until, status: q.status || '草稿',
    items: (q.items || []).map((it) => ({
      name: it.name || '', quantity: Number(it.quantity || 0), unit_price: Number(it.unit_price || 0),
    })),
  })
  quotFormVisible.value = true
}

async function saveQuot() {
  try { await quotFormRef.value?.validate() } catch { return }
  // 明细行合计自动覆盖总金额（无明细时保留手动值）
  if (quotItemsTotal.value > 0) quotForm.total_amount = quotItemsTotal.value
  saving.value = true
  try {
    if (quotForm.id) {
      await updateQuotation(quotForm.id, { ...quotForm })
      ui.toast('报价单已更新', 'success')
    } else {
      await createQuotation({ ...quotForm })
      ui.toast('报价单已创建', 'success')
    }
    quotFormVisible.value = false
    reload('quot')
  } catch (e) {
    ui.toast((e as Error).message, 'error')
  } finally {
    saving.value = false
  }
}

async function onQuotDelete(q: Quotation) {
  try {
    await ElMessageBox.confirm(`确定删除报价单「${q.number || q.id}」吗？`, '删除确认', { type: 'warning' })
  } catch { return }
  try {
    await deleteQuotation(q.id)
    ui.toast('已删除', 'success')
    reload('quot')
  } catch (e) {
    ui.toast((e as Error).message, 'error')
  }
}

// ==================== 合同 ====================
const contractColumns = computed<DataColumn[]>(() => mergeFieldMeta([
  { key: 'number', label: '编号', width: 120 },
  { key: 'title', label: '合同标题', minWidth: 180, asTitle: true },
  { key: 'customer_name', label: '客户', minWidth: 110 },
  { key: 'amount', label: '金额', width: 110, type: 'money' },
  { key: 'status', label: '状态', width: 90, type: 'tag', asTag: true, tagMap: CONTRACT_STATUS_TAG },
  { key: 'start_date', label: '开始', width: 100, type: 'date' },
  { key: 'end_date', label: '结束', width: 100, type: 'date' },
  { key: 'auto_generate_tasks', label: '自动巡检', width: 90, type: 'tag',
    tagMap: { true: 'success', false: 'info' }, valueMap: BOOL_LABELS,
    cellClass: (r) => (r.auto_generate_tasks ? 'gen-on' : '') },
  { key: 'actions', label: '操作', width: 110, type: 'action', fixed: 'right',
    actions: [
      { label: '编辑', type: 'primary', link: true, perm: 'sales:edit', icon: 'Edit',
        onClick: (row) => openContractEdit(row as unknown as ContractItem) },
      { label: '删除', type: 'danger', link: true, perm: 'sales:delete', icon: 'Delete',
        onClick: (row) => onContractDelete(row as unknown as ContractItem) },
    ] },
], fieldMeta.contract || []))

interface ContractFormModel {
  id?: number
  number: string
  title: string
  customer_id: number | null
  amount: number
  status: string
  start_date: string
  end_date: string
  inspection_frequency: string
  task_template_id: number | null
  auto_generate_tasks: boolean
}

const contractFormVisible = ref(false)
const contractFormRef = ref()
const contractForm = reactive<ContractFormModel>(blankContractForm())

function blankContractForm(): ContractFormModel {
  return {
    id: undefined, number: '', title: '', customer_id: null, amount: 0,
    status: '执行中', start_date: '', end_date: '', inspection_frequency: '',
    task_template_id: null, auto_generate_tasks: false,
  }
}

const contractFormRules = { title: [{ required: true, message: '请输入合同标题', trigger: 'blur' }] }

function openContractCreate() {
  Object.assign(contractForm, blankContractForm())
  contractFormVisible.value = true
}

function openContractEdit(c: ContractItem) {
  Object.assign(contractForm, blankContractForm(), {
    id: c.id, number: c.number, title: c.title, customer_id: c.customer_id,
    amount: c.amount, status: c.status || '执行中', start_date: c.start_date,
    end_date: c.end_date, inspection_frequency: c.inspection_frequency,
    task_template_id: c.task_template_id, auto_generate_tasks: c.auto_generate_tasks,
  })
  contractFormVisible.value = true
}

async function saveContract() {
  try { await contractFormRef.value?.validate() } catch { return }
  saving.value = true
  try {
    const res = contractForm.id
      ? await updateContract(contractForm.id, { ...contractForm })
      : await createContract({ ...contractForm })
    const msg = contractForm.id ? '合同已更新' : '合同已创建'
    ui.toast(res.generated ? `${msg}，已生成 ${res.generated} 个巡检任务` : msg, 'success')
    contractFormVisible.value = false
    reload('contract')
  } catch (e) {
    ui.toast((e as Error).message, 'error')
  } finally {
    saving.value = false
  }
}

async function onContractDelete(c: ContractItem) {
  try {
    await ElMessageBox.confirm(`确定删除合同「${c.title}」吗？`, '删除确认', { type: 'warning' })
  } catch { return }
  try {
    await deleteContract(c.id)
    ui.toast('已删除', 'success')
    reload('contract')
  } catch (e) {
    ui.toast((e as Error).message, 'error')
  }
}

// ==================== 项目 ====================
const projectColumns = computed<DataColumn[]>(() => mergeFieldMeta([
  { key: 'name', label: '项目名称', minWidth: 180, asTitle: true },
  { key: 'customer_name', label: '客户', minWidth: 110 },
  { key: 'contract_title', label: '关联合同', minWidth: 130 },
  { key: 'manager', label: '负责人', width: 90 },
  { key: 'status', label: '状态', width: 90, type: 'tag', asTag: true, tagMap: PROJECT_STATUS_TAG },
  { key: 'progress', label: '进度', width: 80, cellClass: (r) => (Number(r.progress) >= 100 ? 'prog-done' : '') },
  { key: 'budget', label: '预算', width: 110, type: 'money' },
  { key: 'actions', label: '操作', width: 110, type: 'action', fixed: 'right',
    actions: [
      { label: '编辑', type: 'primary', link: true, perm: 'sales:edit', icon: 'Edit',
        onClick: (row) => openProjectEdit(row as unknown as ProjectItem) },
      { label: '删除', type: 'danger', link: true, perm: 'sales:delete', icon: 'Delete',
        onClick: (row) => onProjectDelete(row as unknown as ProjectItem) },
    ] },
], fieldMeta.project || []))

interface ProjectFormModel {
  id?: number
  name: string
  contract_id: number | null
  customer_id: number | null
  manager: string
  status: string
  start_date: string
  end_date: string
  progress: number
  budget: number
}

const projectFormVisible = ref(false)
const projectFormRef = ref()
const projectForm = reactive<ProjectFormModel>(blankProjectForm())

function blankProjectForm(): ProjectFormModel {
  return {
    id: undefined, name: '', contract_id: null, customer_id: null, manager: '',
    status: '未启动', start_date: '', end_date: '', progress: 0, budget: 0,
  }
}

const projectFormRules = { name: [{ required: true, message: '请输入项目名称', trigger: 'blur' }] }

function openProjectCreate() {
  Object.assign(projectForm, blankProjectForm())
  projectFormVisible.value = true
}

function openProjectEdit(p: ProjectItem) {
  Object.assign(projectForm, blankProjectForm(), {
    id: p.id, name: p.name, contract_id: p.contract_id, customer_id: p.customer_id,
    manager: p.manager, status: p.status || '未启动', start_date: p.start_date,
    end_date: p.end_date, progress: p.progress, budget: p.budget,
  })
  projectFormVisible.value = true
}

async function saveProject() {
  try { await projectFormRef.value?.validate() } catch { return }
  saving.value = true
  try {
    if (projectForm.id) {
      await updateProject(projectForm.id, { ...projectForm })
      ui.toast('项目已更新', 'success')
    } else {
      await createProject({ ...projectForm })
      ui.toast('项目已创建', 'success')
    }
    projectFormVisible.value = false
    reload('project')
  } catch (e) {
    ui.toast((e as Error).message, 'error')
  } finally {
    saving.value = false
  }
}

async function onProjectDelete(p: ProjectItem) {
  try {
    await ElMessageBox.confirm(`确定删除项目「${p.name}」吗？`, '删除确认', { type: 'warning' })
  } catch { return }
  try {
    await deleteProject(p.id)
    ui.toast('已删除', 'success')
    reload('project')
  } catch (e) {
    ui.toast((e as Error).message, 'error')
  }
}

onMounted(() => {
  fetchSalesDicts().then((d) => (dicts.value = d))
  fetchEntityMetas(['opportunity', 'quotation', 'contract', 'project']).then((metas) => {
    Object.entries(metas).forEach(([name, metadata]) => {
      fieldMeta[name] = metadata.profiles.list || []
    })
  })
})
</script>

<style scoped>
.tabs-card { border-radius: 10px; }
.module-tabs { padding: 0 4px; }
.tab-toolbar { display: flex; justify-content: space-between; gap: 12px; flex-wrap: wrap; margin-bottom: 12px; }
.filter-row { display: flex; gap: 8px; flex-wrap: wrap; align-items: center; }
.filter-search { width: 220px; max-width: 100%; }
.filter-item { width: 130px; max-width: 100%; }
.w-full { width: 100%; }
.gen-on { color: var(--el-color-success); font-weight: 600; }
.prog-done { color: var(--el-color-success); font-weight: 600; }
</style>
