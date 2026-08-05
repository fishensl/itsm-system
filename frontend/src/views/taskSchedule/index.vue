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
      <div v-for="st in ['待执行', '执行中', '待审核', '已完成']" :key="st" class="board-col">
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
    <el-drawer v-model="detailVisible" :title="detail ? detail.title : ''" size="520px">
      <template v-if="detail">
        <el-form label-width="90px">
          <el-form-item label="状态">
            <el-select v-if="detail.status !== '待审核'" :model-value="detail.status" size="small" style="width: 160px"
              @change="(v: string) => quickUpdate({ status: v })">
              <el-option v-for="s in ['待执行', '执行中', '已完成', '已取消']" :key="s" :label="s" :value="s" />
            </el-select>
            <el-tag v-else size="small" type="warning">待审核（报告审核中，不可手工改状态）</el-tag>
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

        <!-- 关联巡检记录（V21 闭环） -->
        <el-divider content-position="left">巡检记录</el-divider>
        <div v-if="record" class="record-block">
          <el-descriptions :column="2" size="small" border>
            <el-descriptions-item label="审核状态">
              <el-tag size="small" :type="REVIEW_TAG[record.review_status] || 'info'">{{ record.review_status }}</el-tag>
            </el-descriptions-item>
            <el-descriptions-item label="巡检员">{{ record.inspector_name || '-' }}</el-descriptions-item>
            <el-descriptions-item label="巡检日期">{{ record.inspection_date || '-' }}</el-descriptions-item>
            <el-descriptions-item label="现场报告">
              <el-link v-if="record.submitted_report_name" type="primary" :underline="false"
                @click="downloadLatestReport">下载</el-link>
              <span v-else>-</span>
            </el-descriptions-item>
          </el-descriptions>
          <div class="record-conclusion" v-if="record.conclusion">结论：{{ record.conclusion }}</div>
          <VersionTimeline v-if="versions.length" :versions="versions" entity-type="inspection" />
          <el-button v-if="canUpload" type="primary" size="small" :icon="Document" class="mt-2" @click="openUpload">
            {{ record ? '重新上传报告（退回后修改重传）' : '上传巡检报告并提交审核' }}
          </el-button>
        </div>
        <el-empty v-else description="尚无巡检记录" :image-size="50">
          <el-button v-if="canUpload" type="primary" size="small" :icon="Document" @click="openUpload">
            上传巡检报告
          </el-button>
        </el-empty>

        <el-button type="danger" plain :loading="deleting" @click="onDelete(detail)" class="mt-2">删除任务</el-button>
      </template>
    </el-drawer>

    <!-- 上传提交资料（全套：报告 + 配置备份 + 拓扑图 + 资产清单） -->
    <el-dialog v-model="uploadVisible" title="上传巡检资料并提交审核" width="680px" destroy-on-close>
      <el-form label-width="100px">
        <!-- 巡检报告 -->
        <el-form-item :label="assetLabel('report')" :required="isRequired('report')">
          <div class="asset-row">
            <el-upload ref="reportUploadRef" :auto-upload="false" :limit="1"
              accept=".doc,.docx,.pdf,.xlsx,.xls,.png,.jpg,.jpeg,.gif,.bmp,.webp,.zip"
              :on-change="(f: UploadFile) => uploadFile = f.raw ?? null" :on-remove="() => uploadFile = null">
              <el-button size="small" :icon="UploadFilled">选择报告文件</el-button>
            </el-upload>
            <span v-if="!uploadFile && isRequired('report')" class="skip-box">
              <el-input v-model="skipReasons.report" size="small" placeholder="上传不了？填原因即可提交" style="width: 300px" />
            </span>
          </div>
        </el-form-item>
        <el-form-item label="结论">
          <el-input v-model="uploadConclusion" type="textarea" :rows="2"
            placeholder="本次巡检结论（可选），如：设备运行正常，无异常" />
        </el-form-item>
        <el-form-item label="提交备注">
          <el-input v-model="uploadRemark" type="textarea" :rows="2"
            placeholder="不便写入报告的实际情况（可选），将随本次提交留档" />
        </el-form-item>

        <!-- 完整配置备份包 -->
        <el-form-item :label="assetLabel('config_zip')" :required="isRequired('config_zip')">
          <div class="asset-row">
            <el-upload :auto-upload="false" :limit="1" accept=".zip"
              :on-change="(f: UploadFile) => configZipFile = f.raw ?? null" :on-remove="() => configZipFile = null">
              <el-button size="small" :icon="UploadFilled">选择配置备份包（zip）</el-button>
            </el-upload>
            <el-select v-if="configZipFile" v-model="configZipDeviceId" size="small" clearable filterable
              placeholder="所属设备（核心设备）" style="width: 200px">
              <el-option v-for="d in devices" :key="d.id" :label="d.device_name" :value="d.id" />
            </el-select>
            <span v-if="!configZipFile && isRequired('config_zip')" class="skip-box">
              <el-input v-model="skipReasons.config_zip" size="small" placeholder="上传不了？填原因即可提交" style="width: 300px" />
            </span>
          </div>
        </el-form-item>

        <!-- 核心设备文本配置（动态行） -->
        <el-form-item :label="assetLabel('config_text')" :required="isRequired('config_text')">
          <div class="asset-col">
            <div v-for="(row, i) in configTextRows" :key="i" class="asset-row">
              <el-select v-model="row.device_id" size="small" clearable filterable placeholder="设备"
                style="width: 160px">
                <el-option v-for="d in devices" :key="d.id" :label="d.device_name" :value="d.id" />
              </el-select>
              <el-upload :auto-upload="false" :limit="1" accept=".txt,.cfg,.conf,.log,.text"
                :on-change="(f: UploadFile) => { row.file = f.raw ?? null; if (row.file) row.content = '' }"
                :on-remove="() => row.file = null">
                <el-button size="small" :icon="UploadFilled">文件</el-button>
              </el-upload>
              <el-input v-model="row.content" size="small" type="textarea" :rows="2" placeholder="或直接粘贴配置内容"
                style="width: 260px" />
              <el-button size="small" link type="danger" :icon="Delete" @click="configTextRows.splice(i, 1)" />
            </div>
            <el-button size="small" plain :icon="Plus" @click="configTextRows.push({ device_id: null, file: null, content: '' })">
              添加设备配置
            </el-button>
            <span v-if="!configTextRows.length && isRequired('config_text')" class="skip-box">
              <el-input v-model="skipReasons.config_text" size="small" placeholder="上传不了？填原因即可提交" style="width: 300px" />
            </span>
          </div>
        </el-form-item>

        <!-- 拓扑图 -->
        <el-form-item :label="assetLabel('topology')" :required="isRequired('topology')">
          <div class="asset-row">
            <el-upload :auto-upload="false" :limit="1"
              accept=".png,.jpg,.jpeg,.gif,.bmp,.webp,.pdf,.vsd,.vsdx,.drawio,.xml"
              :on-change="(f: UploadFile) => topologyFile = f.raw ?? null" :on-remove="() => topologyFile = null">
              <el-button size="small" :icon="UploadFilled">选择拓扑图文件</el-button>
            </el-upload>
            <span class="asset-tip">上传后同步到设备管理-该客户拓扑图</span>
            <span v-if="!topologyFile && isRequired('topology')" class="skip-box">
              <el-input v-model="skipReasons.topology" size="small" placeholder="上传不了？填原因即可提交" style="width: 300px" />
            </span>
          </div>
        </el-form-item>

        <!-- 资产清单 -->
        <el-form-item :label="assetLabel('asset_list')" :required="isRequired('asset_list')">
          <div class="asset-row">
            <el-upload :auto-upload="false" :limit="1" accept=".xlsx,.xls"
              :on-change="(f: UploadFile) => assetListFile = f.raw ?? null" :on-remove="() => assetListFile = null">
              <el-button size="small" :icon="UploadFilled">选择资产清单 Excel</el-button>
            </el-upload>
            <span class="asset-tip">提交时解析导入设备（按设备名更新/新增，列与设备导入模板一致）</span>
            <span v-if="!assetListFile && isRequired('asset_list')" class="skip-box">
              <el-input v-model="skipReasons.asset_list" size="small" placeholder="上传不了？填原因即可提交" style="width: 300px" />
            </span>
          </div>
        </el-form-item>

        <el-form-item v-if="uploadHint" label="提示">
          <span class="upload-hint">{{ uploadHint }}</span>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="uploadVisible = false">取消</el-button>
        <el-button type="primary" :loading="uploading" @click="doUpload">上传并提交审核</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onMounted } from 'vue'
import { ElMessageBox, type UploadFile } from 'element-plus'
import { Plus, Search, Download, Upload, UploadFilled, Document, Delete } from '@element-plus/icons-vue'
import {
  fetchTaskSchedule, createTaskSchedule, updateTaskSchedule, deleteTaskSchedule,
  batchTaskSchedule, fetchImportTemplate, importTaskSchedule, downloadBase64,
  type TaskScheduleData, type TaskScheduleItem,
} from '@/api/taskSchedule'
import { fetchInspections, fetchInspection, fetchInspectionVersions, uploadTaskReport,
  versionReportUrl, type Inspection, type SubmissionVersion } from '@/api/inspections'
import VersionTimeline from '@/components/VersionTimeline.vue'
import { useUserStore } from '@/stores/user'
import { useUiStore } from '@/stores/ui'

const user = useUserStore()
const ui = useUiStore()
const data = ref<TaskScheduleData | null>(null)
const loading = ref(false)
const query = reactive<Record<string, unknown>>({ view: 'engineer', period: 'this_quarter', q: '' })
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

// V21/V22: 关联巡检记录 + 上传全套资料
const record = ref<Inspection | null>(null)
const versions = ref<SubmissionVersion[]>([])
const uploadVisible = ref(false)
const uploading = ref(false)
const uploadFile = ref<File | null>(null)
const uploadConclusion = ref('')
const uploadRemark = ref('')
const devices = ref<Array<{ id: number; device_name: string; device_type: string }>>([])
const requiredAssets = ref<Record<string, boolean>>({})
const configZipFile = ref<File | null>(null)
const configZipDeviceId = ref<number | null>(null)
const configTextRows = ref<Array<{ device_id: number | null; file: File | null; content: string }>>([])
const topologyFile = ref<File | null>(null)
const assetListFile = ref<File | null>(null)
const skipReasons = reactive<Record<string, string>>({
  report: '', config_zip: '', config_text: '', topology: '', asset_list: '',
})

const ASSET_LABELS: Record<string, string> = {
  report: '巡检报告', config_zip: '完整配置备份包', config_text: '核心设备文本配置',
  topology: '拓扑图', asset_list: '资产清单',
}

function isRequired(key: string) {
  return !!requiredAssets.value[key]
}

function assetLabel(key: string) {
  return (isRequired(key) ? '* ' : '') + ASSET_LABELS[key]
}
const uploadHint = computed(() => {
  const st = detail.value?.status
  if (st === '待审核') return '任务正在审核中，请等待审核结果后再上传'
  if (st === '已完成') return '任务已完成，如需补充请先改回执行中'
  if (st === '已取消') return '任务已取消，不可上传'
  if (record.value?.review_status === '待审核') return '已有报告在审核中，请等待审核结果'
  return ''
})
const canUpload = computed(() =>
  user.hasPerm('inspection:edit') && !!detail.value &&
  ['待执行', '执行中', '待审核'].includes(detail.value.status),
)
const REVIEW_TAG: Record<string, 'primary' | 'success' | 'warning' | 'danger' | 'info'> = {
  草稿: 'info',
  待审核: 'warning',
  已通过: 'success',
  已退回: 'danger',
}

const kpiCards = computed(() => {
  const k = data.value?.kpi
  if (!k) return []
  return [
    { key: 'total', label: '总任务', value: k.total, cls: '' },
    { key: 'pending', label: '待执行', value: k.pending, cls: 'warning' },
    { key: 'running', label: '执行中', value: k.running, cls: 'primary' },
    { key: 'reviewing', label: '待审核', value: k.reviewing, cls: 'info' },
    { key: 'done', label: '已完成', value: k.done, cls: 'success' },
    { key: 'overdue', label: '逾期', value: k.overdue, cls: 'danger' },
    { key: 'est', label: '预估人天', value: k.est_effort, cls: '' },
    { key: 'act', label: '实际人天', value: k.act_effort, cls: '' },
  ]
})

function priorityType(p: string) {
  return { 低: 'info', 中: '', 高: 'warning', 紧急: 'danger' }[p] || 'info'
}

// 任务状态配色：待执行=橙 / 执行中=深蓝 / 待审核=青 / 已完成=绿 / 已取消=灰；红色留给「逾期」
// 统一 effect="dark"（深底白字）：浅色模式下对比度也足够，深浅模式表现一致
function statusType(s: string) {
  return { 待执行: 'warning', 执行中: 'primary', 待审核: 'info', 已完成: 'success', 已取消: 'info' }[s] || 'info'
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
  loadRecord()
}

async function loadRecord() {
  record.value = null
  versions.value = []
  if (!detail.value) return
  try {
    const page = await fetchInspections({ task_id: detail.value.id, page_size: 1 })
    const row = page.items?.[0]
    if (row) {
      const [full, vers] = await Promise.all([
        fetchInspection(row.id),
        fetchInspectionVersions(row.id),
      ])
      record.value = full
      versions.value = vers
    }
  } catch { /* toast */ }
}

function openUpload() {
  uploadFile.value = null
  uploadConclusion.value = ''
  uploadRemark.value = ''
  configZipFile.value = null
  configZipDeviceId.value = null
  configTextRows.value = []
  topologyFile.value = null
  assetListFile.value = null
  Object.assign(skipReasons, { report: '', config_zip: '', config_text: '', topology: '', asset_list: '' })
  uploadVisible.value = true
  if (detail.value) {
    fetch(`/api/task-schedule/${detail.value.id}/required-assets`)
      .then((r) => r.json())
      .then((body) => {
        if (body?.code === 0) {
          requiredAssets.value = body.data.required_assets || {}
          devices.value = body.data.devices || []
        }
      })
      .catch(() => { /* toast */ })
  }
}

function downloadLatestReport() {
  const latest = versions.value.slice().reverse().find((v) => v.report_file)
  const rid = latest?.id ?? 0
  if (rid) window.open(versionReportUrl('inspection', rid), '_blank')
}

async function doUpload() {
  if (!detail.value) return
  if (!uploadFile.value && !skipReasons.report.trim()) {
    ui.toast('请选择巡检报告文件，或填写无法上传的原因', 'warning')
    return
  }
  uploading.value = true
  try {
    const fd = new FormData()
    if (uploadFile.value) fd.append('report_file', uploadFile.value)
    else fd.append('report_skip_reason', skipReasons.report)
    fd.append('conclusion', uploadConclusion.value)
    fd.append('remark', uploadRemark.value)

    if (configZipFile.value) {
      fd.append('config_zip', configZipFile.value)
      if (configZipDeviceId.value) fd.append('config_zip_device_id', String(configZipDeviceId.value))
    } else if (skipReasons.config_zip) {
      fd.append('config_zip_skip_reason', skipReasons.config_zip)
    }

    configTextRows.value.forEach((row, i) => {
      if (row.file) {
        fd.append(`config_text_file_${i}`, row.file)
        if (row.device_id) fd.append(`config_text_device_id_${i}`, String(row.device_id))
      } else if (row.content.trim()) {
        fd.append(`config_text_content_${i}`, row.content)
        if (row.device_id) fd.append(`config_text_device_id_${i}`, String(row.device_id))
      }
    })
    if (!configTextRows.value.some((r) => r.file || r.content.trim()) && skipReasons.config_text) {
      fd.append('config_text_skip_reason', skipReasons.config_text)
    }

    if (topologyFile.value) fd.append('topology_file', topologyFile.value)
    else if (skipReasons.topology) fd.append('topology_skip_reason', skipReasons.topology)

    if (assetListFile.value) fd.append('asset_list', assetListFile.value)
    else if (skipReasons.asset_list) fd.append('asset_list_skip_reason', skipReasons.asset_list)

    const r = await uploadTaskReport(detail.value.id, fd)
    let msg = `已上传（版本 ${r.version_no}）并提交审核，任务状态：${r.task_status}`
    if (r.asset_import) {
      msg += `；资产清单导入：新增 ${r.asset_import.created} 台、更新 ${r.asset_import.updated} 台`
    }
    if (r.skipped.length) {
      msg += `；豁免：${r.skipped.map(([label]) => label).join('、')}`
    }
    ui.toast(msg, 'success')
    uploadVisible.value = false
    await loadRecord()
    reload()
  } catch (e) {
    ui.toast((e as Error).message, 'error')
  } finally {
    uploading.value = false
  }
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
.col-待审核 { color: var(--el-color-info); border-bottom: 3px solid var(--el-color-info); }
.col-已完成 { color: var(--el-color-success); border-bottom: 3px solid var(--el-color-success); }
.col-engineer { border-bottom: 3px solid var(--el-color-info); }
.col-count { font-size: 12px; color: var(--itsm-text-muted); }
.col-check { margin: 6px 12px; }
.col-body { padding: 6px 10px 12px; min-height: 80px; }
.record-block { margin-bottom: 10px; }
.record-conclusion { font-size: 13px; margin: 8px 0; white-space: pre-wrap; }
.upload-hint { color: var(--el-color-warning); font-size: 12px; }
.mt-2 { margin-top: 8px; }
.asset-row { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; width: 100%; }
.asset-col { display: flex; flex-direction: column; gap: 8px; width: 100%; }
.asset-tip { font-size: 12px; color: var(--itsm-text-muted); }
.skip-box { display: inline-flex; }
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
