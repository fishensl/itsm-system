<template>
  <div class="page-container">
    <div class="page-header">
      <h2 class="page-title">巡检记录</h2>
      <div class="header-actions">
        <el-button :icon="Download" plain @click="doExport('excel')">导出记录</el-button>
        <el-button :icon="FolderOpened" plain @click="doExport('zip')">导出报告包</el-button>
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
        <el-date-picker v-model="dateRange" type="daterange" value-format="YYYY-MM-DD" start-placeholder="开始日期"
          end-placeholder="结束日期" class="filter-item date-range" @change="onDateChange" />
        <el-checkbox v-model="incompleteOnly" @change="reload">仅看不完整</el-checkbox>
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
      size="600px" destroy-on-close>
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
          <el-descriptions-item label="关联任务">
            {{ detail.task_title || '-' }}
          </el-descriptions-item>
          <el-descriptions-item label="巡检日期">{{ detail.inspection_date || '-' }}</el-descriptions-item>
          <el-descriptions-item label="巡检人员">{{ detail.inspector_name || '-' }}</el-descriptions-item>
          <el-descriptions-item label="现场报告">
            <el-link v-if="detail.submitted_report_name" type="primary" :underline="false"
              @click="downloadLatest">下载</el-link>
            <span v-else class="text-muted">无</span>
          </el-descriptions-item>
          <el-descriptions-item label="正式报告">
            <el-link v-if="detail.report_file && detail.report_file_name" type="primary" :underline="false"
              @click="downloadFormal">下载</el-link>
            <span v-else class="text-muted">未生成</span>
          </el-descriptions-item>
          <el-descriptions-item label="资料完整">
            <el-tag size="small" :type="detail.complete ? 'success' : 'warning'">
              {{ detail.complete ? '完整' : '缺:' + (detail.missing_fields || []).join('、') }}
            </el-tag>
          </el-descriptions-item>
          <el-descriptions-item label="巡检地点">{{ detail.location || '-' }}</el-descriptions-item>
          <el-descriptions-item label="创建时间">{{ detail.created_at }}</el-descriptions-item>
        </el-descriptions>

        <el-divider content-position="left">结论</el-divider>
        <p class="detail-text">{{ detail.conclusion || '-' }}</p>

        <template v-if="detail.review_comment">
          <el-divider content-position="left">审核意见</el-divider>
          <p class="detail-text review-comment">{{ detail.review_comment }}</p>
        </template>

        <!-- 提交审核记录时间线 -->
        <el-divider content-position="left">提交审核记录（每次上传 + 每轮审核）</el-divider>
        <VersionTimeline :versions="versions" entity-type="inspection" />

        <!-- 审核操作 -->
        <el-divider content-position="left">操作</el-divider>
        <div class="action-bar">
          <template v-if="detail.review_status === '草稿'">
            <el-button v-if="user.hasPerm('inspection:edit')" size="small" type="primary"
              @click="onSubmit">提交审核</el-button>
          </template>
          <template v-else-if="detail.review_status === '待审核'">
            <el-button v-if="user.hasPerm('inspection:review')" size="small" type="success"
              @click="openReview(true)">审核通过</el-button>
            <el-button v-if="user.hasPerm('inspection:review')" size="small" type="danger"
              @click="openReview(false)">退回修改</el-button>
          </template>
          <el-button v-if="user.hasPerm('inspection:edit')" size="small" type="primary" plain
            @click="openEdit(detail)">编辑</el-button>
          <el-button v-if="user.hasPerm('inspection:delete')" size="small" type="danger" plain
            @click="onDelete(detail)">删除</el-button>
        </div>
      </div>
    </el-drawer>

    <!-- 审核弹窗（双栏：报告在线预览 + 检查项清单勾选） -->
    <el-dialog v-model="reviewVisible" :title="reviewApproved ? '审核通过' : '退回修改'" width="1080px"
      top="4vh" destroy-on-close>
      <div class="review-layout">
        <!-- 左栏：报告预览 -->
        <div class="review-preview">
          <div class="preview-tabs">
            <el-radio-group v-model="previewTab" size="small">
              <el-radio-button value="report">现场报告</el-radio-button>
              <el-radio-button v-if="pendingTextAsset" value="config_text">文本配置</el-radio-button>
              <el-radio-button value="formal" :disabled="!formalReportName">正式报告</el-radio-button>
            </el-radio-group>
          </div>
          <div v-if="previewTab === 'report'" class="preview-body">
            <FilePreview v-if="pendingVersion?.report_file" :url="pendingVersionUrl" :file-name="pendingVersion.report_name" />
            <el-empty v-else description="该版本未上传现场报告（豁免提交）" :image-size="60" />
          </div>
          <div v-else-if="previewTab === 'config_text'" class="preview-body">
            <FilePreview :text="pendingTextAsset?.content_text || ''" :file-name="pendingTextAsset?.file_name" />
          </div>
          <div v-else class="preview-body">
            <FilePreview :url="formalReportUrl2" :file-name="formalReportName" />
          </div>
        </div>

        <!-- 右栏：检查项 + 审核表单（label 置顶避免窄栏重叠） -->
        <div class="review-panel">
          <el-form label-position="top">
            <div class="checklist-title">审核检查项<span class="checklist-hint">逐项核对，全程留痕</span></div>
            <div v-for="item in checklistItems" :key="item.name" class="check-item">
              <span class="check-name">{{ item.name }}</span>
              <el-radio-group v-model="checklistValue[item.name]" size="small" @change="autoFillRequirements">
                <el-radio-button value="合格">合格</el-radio-button>
                <el-radio-button value="需修改">需修改</el-radio-button>
                <el-radio-button value="不适用">不适用</el-radio-button>
              </el-radio-group>
            </div>

            <template v-if="reviewApproved">
              <el-divider />
              <el-form-item label="审核意见">
                <el-input v-model="reviewRemark" type="textarea" :rows="3" placeholder="审核意见（可选）" />
              </el-form-item>
            </template>
            <template v-else>
              <el-divider />
              <el-form-item label="退回原因" required>
                <el-input v-model="reviewRemark" type="textarea" :rows="2"
                  placeholder="如：报告缺少现场照片、数据有误" />
              </el-form-item>
              <el-form-item label="需要修改" required>
                <el-input v-model="reviewRequirements" type="textarea" :rows="3"
                  placeholder="将按需修改检查项自动生成，可编辑补充" />
              </el-form-item>
            </template>
          </el-form>
          <!-- AI 辅助分析 -->
          <el-divider content-position="left">AI 辅助分析</el-divider>
          <div class="ai-box">
            <el-button v-if="!aiLoading && !aiResult" size="small" plain type="primary" :icon="MagicStick"
              @click="runAiAnalyze">生成分析建议</el-button>
            <div v-if="aiLoading" v-loading="true" class="ai-loading">AI 分析中，请稍候…</div>
            <div v-else-if="aiResult" class="ai-result">
              <div class="ai-result-head">
                <span class="ai-result-title">AI 建议</span>
                <el-button size="small" link type="primary" @click="aiResult = ''">重新分析</el-button>
              </div>
              <pre class="ai-text">{{ aiResult }}</pre>
            </div>
          </div>
          <div class="review-actions">
            <el-button @click="reviewVisible = false">取消</el-button>
            <el-button type="primary" :loading="reviewing" @click="doReview">
              {{ reviewApproved ? '审核通过' : '退回修改' }}
            </el-button>
          </div>
        </div>
      </div>
    </el-dialog>

    <!-- 新建/编辑巡检 -->
    <el-dialog v-model="formVisible" :title="form.id ? '编辑巡检' : '新建巡检'" width="600px" top="5vh"
      destroy-on-close>
      <el-form ref="formRef" :model="form" :rules="formRules" label-width="90px">
        <el-form-item label="巡检任务" prop="task_id">
          <el-select v-if="!form.id" v-model="form.task_id" filterable clearable class="w-full"
            placeholder="必选：选择任务后自动带出客户/日期/工程师" @change="onTaskSelect">
            <el-option v-for="t in selectableTasks" :key="t.id" :label="`${t.title}（${t.customer_name || '-'}）`"
              :value="t.id" />
          </el-select>
          <span v-else>{{ form.task_title || '-' }}</span>
        </el-form-item>
        <el-form-item label="标题" prop="title">
          <el-input v-model="form.title" placeholder="必填，如：核心机房月度巡检" />
        </el-form-item>
        <el-row :gutter="12">
          <el-col :xs="24" :sm="12">
            <el-form-item label="客户" prop="customer_id">
              <el-select v-model="form.customer_id" filterable clearable class="w-full" placeholder="从任务自动带出">
                <el-option v-for="c in regionCustomers" :key="c.id" :label="c.name" :value="c.id" />
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
        <el-form-item v-if="!form.id" label="现场报告">
          <el-upload ref="reportUploadRef" drag :auto-upload="false" :limit="1" accept=".doc,.docx,.pdf,.xlsx,.xls,.png,.jpg,.jpeg,.gif,.bmp,.webp,.zip"
            :on-change="onReportChange" :on-remove="() => form.reportFile = null">
            <el-icon class="el-icon--upload"><UploadFilled /></el-icon>
            <div class="el-upload__text">拖拽或点击上传现场报告（可选，创建后直接进入提交审核）</div>
          </el-upload>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="formVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="save">{{ form.id ? '保存' : '创建' }}</el-button>
      </template>
    </el-dialog>

    <!-- 提交审核引导：无现场报告时上传 -->
    <el-dialog v-model="submitReportVisible" title="上传现场报告并提交审核" width="480px" destroy-on-close>
      <el-upload ref="submitReportUploadRef" drag :auto-upload="false" :limit="1"
        accept=".doc,.docx,.pdf,.xlsx,.xls,.png,.jpg,.jpeg,.gif,.bmp,.webp,.zip"
        :on-change="onSubmitReportChange" :on-remove="() => submitReportFile = null">
        <el-icon class="el-icon--upload"><UploadFilled /></el-icon>
        <div class="el-upload__text">拖拽或点击上传现场报告（Word/PDF/Excel/图片）</div>
      </el-upload>
      <template #footer>
        <el-button @click="submitReportVisible = false">取消</el-button>
        <el-button type="primary" :loading="submittingReport" @click="doSubmitReport">上传并提交审核</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import type { UploadFile } from 'element-plus/es/components/upload'
import { ElMessageBox } from 'element-plus/es/components/message-box/index'
import { ref, reactive, computed, onMounted } from 'vue'
import { Plus, Search, Download, FolderOpened, UploadFilled, MagicStick } from '@element-plus/icons-vue'
import DataTable, { type DataColumn } from '@/components/DataTable.vue'
import VersionTimeline from '@/components/VersionTimeline.vue'
import FilePreview from '@/components/FilePreview.vue'
import { useUserStore } from '@/stores/user'
import { useUiStore } from '@/stores/ui'
import {
  fetchInspections, fetchInspection, createInspection, updateInspection, deleteInspection,
  submitInspection, reviewInspection, analyzeInspectionAI, fetchInspectionDicts, fetchInspectionVersions,
  fetchReviewChecklist,
  versionReportUrl, formalReportUrl, inspectionExportUrl,
  inspectionReportsZipUrl,
  OVERALL_STATUS_TAG, REVIEW_STATUS_TAG, type Inspection, type InspectionDicts,
  type InspectionTaskOption, type SubmissionVersion, type ReviewChecklistItem,
} from '@/api/inspections'

const user = useUserStore()
const ui = useUiStore()
const dicts = ref<InspectionDicts | null>(null)

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

const query = reactive<Record<string, unknown>>({
  search: '', status: '', review_status: '', customer_id: undefined,
})
const dateRange = ref<[string, string] | null>(null)
const incompleteOnly = ref(false)
const tableRef = ref()

const columns = computed<DataColumn[]>(() => [
  { key: 'title', label: '标题', minWidth: 180, asTitle: true },
  { key: 'customer_name', label: '客户', minWidth: 100 },
  { key: 'inspection_date', label: '巡检日期', width: 100 },
  { key: 'inspector_name', label: '巡检人员', width: 90 },
  { key: 'overall_status', label: '总体状态', width: 90, type: 'tag', asTag: true,
    tagMap: OVERALL_STATUS_TAG },
  { key: 'review_status', label: '审核状态', width: 90, type: 'tag', tagMap: REVIEW_STATUS_TAG },
  { key: 'complete', label: '资料完整', width: 100, type: 'tag',
    tagMap: { true: 'success', false: 'warning' } as Record<string, 'success' | 'warning'>,
    valueMap: { true: '完整', false: '不完整' } },
  { key: 'report_label', label: '正式报告', width: 80 },
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
const versions = ref<SubmissionVersion[]>([])

async function openDetail(row: Record<string, unknown>) {
  try {
    const [full, vers] = await Promise.all([
      fetchInspection(row.id as number),
      fetchInspectionVersions(row.id as number),
    ])
    detail.value = full
    versions.value = vers
    detailVisible.value = true
  } catch { /* toast */ }
}

function downloadLatest() {
  const latest = versions.value.slice().reverse().find((v) => v.report_file)
  if (!latest || !detail.value) return
  window.open(versionReportUrl('inspection', latest.id), '_blank')
}

function downloadFormal() {
  if (!detail.value?.report_file_name) return
  window.open(formalReportUrl(detail.value.report_file_name), '_blank')
}

async function refreshDetail() {
  if (!detail.value) return
  try {
    const [full, vers] = await Promise.all([
      fetchInspection(detail.value.id),
      fetchInspectionVersions(detail.value.id),
    ])
    detail.value = full
    versions.value = vers
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
    const msg = (e as Error).message
    if (msg.includes('报告')) {
      openSubmitReport()
      return
    }
    ui.toast(msg, 'error')
  }
}

// 提交审核引导弹窗：无现场报告时上传后提交
const submitReportVisible = ref(false)
const submitReportFile = ref<File | null>(null)
const submitReportUploadRef = ref()
const submittingReport = ref(false)

function openSubmitReport() {
  submitReportFile.value = null
  submitReportUploadRef.value?.clearFiles?.()
  submitReportVisible.value = true
}

function onSubmitReportChange(f: UploadFile) {
  submitReportFile.value = f.raw ?? null
}

async function doSubmitReport() {
  if (!detail.value) return
  if (!submitReportFile.value) {
    ui.toast('请选择现场报告文件', 'warning')
    return
  }
  submittingReport.value = true
  try {
    const fd = new FormData()
    fd.append('report_file', submitReportFile.value)
    await submitInspection(detail.value.id, fd)
    ui.toast('已上传并提交审核', 'success')
    submitReportVisible.value = false
    await refreshDetail()
    tableRef.value?.refresh()
  } catch (e) {
    ui.toast((e as Error).message, 'error')
  } finally {
    submittingReport.value = false
  }
}

// 审核弹窗（V23：检查项清单 + 报告预览）
const reviewVisible = ref(false)
const reviewApproved = ref(true)
const reviewRemark = ref('')
const reviewRequirements = ref('')
const reviewing = ref(false)
const checklistItems = ref<ReviewChecklistItem[]>([])
const checklistValue = reactive<Record<string, string>>({})
const previewTab = ref('report')

// AI 辅助分析
const aiLoading = ref(false)
const aiResult = ref('')

async function runAiAnalyze() {
  if (!detail.value) return
  aiLoading.value = true
  aiResult.value = ''
  try {
    const res = await analyzeInspectionAI(detail.value.id)
    aiResult.value = res.analysis
  } catch (e) {
    ui.toast((e as Error).message, 'error')
  } finally {
    aiLoading.value = false
  }
}

const pendingVersion = computed(() => versions.value.find((v) => v.review_status === '待审核'))
const pendingVersionUrl = computed(() =>
  pendingVersion.value?.report_file ? versionReportUrl('inspection', pendingVersion.value.id) : '')
const formalReportName = computed(() => detail.value?.report_file_name || '')
const formalReportUrl2 = computed(() => (formalReportName.value ? formalReportUrl(formalReportName.value) : ''))
const pendingTextAsset = computed(() =>
  pendingVersion.value?.assets?.find((a) => a.asset_type === 'config_text' && a.has_content) || null)

async function openReview(approved: boolean) {
  if (!detail.value) return
  reviewApproved.value = approved
  reviewRemark.value = ''
  reviewRequirements.value = ''
  reviewVisible.value = true
  aiResult.value = ''
  previewTab.value = 'report'
  try {
    const { items } = await fetchReviewChecklist()
    checklistItems.value = items.filter((it) => it.enabled)
    checklistItems.value.forEach((it) => {
      if (!(it.name in checklistValue)) checklistValue[it.name] = '合格'
    })
  } catch { /* toast */ }
}

function autoFillRequirements() {
  const need = checklistItems.value
    .filter((it) => checklistValue[it.name] === '需修改')
    .map((it) => it.name)
  reviewRequirements.value = need.length ? `请完善：${need.join('、')}` : ''
}

async function doReview() {
  if (!detail.value) return
  if (!reviewApproved.value) {
    if (!reviewRemark.value.trim()) {
      ui.toast('请填写退回原因', 'warning')
      return
    }
    if (!reviewRequirements.value.trim()) {
      ui.toast('请填写需要修改的内容（可由检查项自动生成）', 'warning')
      return
    }
  } else {
    const needFix = checklistItems.value.some((it) => checklistValue[it.name] === '需修改')
    if (needFix) {
      try {
        await ElMessageBox.confirm('存在「需修改」检查项，确定仍要审核通过吗？', '确认', { type: 'warning' })
      } catch { return }
    }
  }
  reviewing.value = true
  try {
    const checklist: Record<string, string> = {}
    checklistItems.value.forEach((it) => { checklist[it.name] = checklistValue[it.name] || '合格' })
    await reviewInspection(detail.value.id, reviewApproved.value,
      reviewRemark.value.trim(), reviewRequirements.value.trim(), checklist)
    ui.toast(`${reviewApproved.value ? '审核通过' : '退回修改'}成功`, 'success')
    reviewVisible.value = false
    await refreshDetail()
    tableRef.value?.refresh()
  } catch (e) {
    ui.toast((e as Error).message, 'error')
  } finally {
    reviewing.value = false
  }
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
const reportUploadRef = ref()
const form = reactive<Record<string, unknown>>({
  id: null, title: '', task_id: null, task_title: '', customer_id: null, inspection_date: '',
  inspector_user_id: null, overall_status: '正常', conclusion: '', reportFile: null,
})
const formRules = {
  title: [{ required: true, message: '请输入巡检标题', trigger: 'blur' }],
  task_id: [{ required: true, message: '请选择巡检任务', trigger: 'change' }],
}

const selectableTasks = computed(() =>
  (dicts.value?.tasks || []).filter((t) =>
    t.status !== '已完成' && t.status !== '已取消' && !t.has_record),
)

function blankForm() {
  return { id: null, title: '', task_id: null, task_title: '', customer_id: null,
    inspection_date: '', inspector_user_id: null, overall_status: '正常', conclusion: '',
    reportFile: null }
}

function onReportChange(f: UploadFile) {
  form.reportFile = f.raw ?? null
}

function onTaskSelect(tid: number | undefined) {
  const t = (dicts.value?.tasks || []).find((x) => x.id === tid) as InspectionTaskOption | undefined
  if (!t) return
  form.customer_id = t.customer_id
  form.title = t.title || form.title
  const today = new Date().toISOString().slice(0, 10)
  form.inspection_date = form.inspection_date || today
}

function openCreate() {
  Object.assign(form, blankForm())
  reportUploadRef.value?.clearFiles?.()
  // 驻场工程师：默认选中负责区域的第一个客户（无负责区域用户不受影响；选任务会自动带出客户）
  const first = regionCustomers.value[0]
  if (first && !form.customer_id) form.customer_id = first.id
  formVisible.value = true
}

function openEdit(i: Inspection) {
  Object.assign(form, {
    id: i.id, title: i.title, task_id: i.task_id, task_title: i.task_title,
    customer_id: i.customer_id,
    inspection_date: i.inspection_date || '', overall_status: i.overall_status,
    conclusion: i.conclusion || '', inspector_user_id: i.inspector_user_id ?? null,
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
      const res = await createInspection({ ...form })
      // 创建时上传现场报告 → 直接进入提交审核（补齐"记录页新建"闭环）
      if (form.reportFile) {
        const fd = new FormData()
        fd.append('report_file', form.reportFile as File)
        await submitInspection(res.id, fd)
        ui.toast('巡检记录已创建并提交审核', 'success')
      } else {
        ui.toast('巡检记录已创建', 'success')
      }
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
  const url = kind === 'excel' ? inspectionExportUrl(exportParams()) : inspectionReportsZipUrl(exportParams())
  window.open(url, '_blank')
}

function reload() {
  query.incomplete_only = incompleteOnly.value ? 1 : undefined
  tableRef.value?.refresh()
}

onMounted(() => {
  fetchInspectionDicts().then((d) => (dicts.value = d))
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
.review-comment { color: var(--el-color-danger); font-weight: 600; }
.action-bar { display: flex; gap: 8px; flex-wrap: wrap; align-items: center; }
.task-status-tag { margin-left: 6px; }
.text-muted { color: var(--itsm-text-muted); }
.review-layout { display: flex; gap: 14px; }
.review-preview { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 8px; }
.review-panel { width: 400px; flex-shrink: 0; display: flex; flex-direction: column; }
.review-panel .el-form {
  max-height: 62vh; overflow-y: auto; padding-right: 4px;
}
.preview-tabs { flex-shrink: 0; }
.preview-body { flex: 1; min-height: 380px; max-height: 62vh; overflow: auto; border: 1px solid var(--el-border-color-lighter); border-radius: 6px; padding: 8px; }
.checklist-title { font-weight: 600; font-size: 13px; margin-bottom: 6px; }
.checklist-hint { font-weight: 400; font-size: 12px; color: var(--itsm-text-muted); margin-left: 6px; }
.check-item { display: flex; align-items: center; justify-content: space-between; gap: 6px; flex-wrap: wrap; padding: 5px 0; border-bottom: 1px dashed var(--el-border-color-lighter); }
.check-name { font-size: 13px; flex-shrink: 0; }
.check-item .el-radio-button__inner { padding: 4px 8px; font-size: 12px; }
.review-actions { display: flex; justify-content: flex-end; gap: 8px; margin-top: 10px; flex-shrink: 0; }
.ai-box { margin-bottom: 8px; }
.ai-loading { font-size: 12px; color: var(--itsm-text-muted); padding: 8px 0; min-height: 40px; }
.ai-result {
  border: 1px dashed var(--el-color-primary-light-5);
  background: var(--el-color-primary-light-9);
  border-radius: 8px;
  padding: 10px;
  max-height: 300px;
  overflow: auto;
}
.ai-result-head { display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px; }
.ai-result-title { font-size: 12px; font-weight: 600; color: var(--el-color-primary); }
.ai-text {
  white-space: pre-wrap;
  word-break: break-all;
  font-size: 12px;
  margin: 0;
  line-height: 1.6;
}
</style>
