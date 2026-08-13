<template>
  <div class="page-container">
    <div class="page-header">
      <h2 class="page-title">任务安排</h2>
      <div class="header-actions">
        <el-button plain :icon="Download" @click="downloadTemplate">导入模板</el-button>
        <input ref="importInput" type="file" accept=".xlsx,.xls" style="display: none" @change="onImportFile" />
        <el-button plain :icon="Upload" @click="importInput?.click()">批量导入</el-button>
        <el-button plain :type="bulkMode ? 'primary' : undefined" @click="toggleBulkMode">
          {{ bulkMode ? '退出批量' : '批量操作' }}
        </el-button>
        <el-button v-if="user.hasPerm('task:schedule')" type="primary" :icon="Plus" @click="openCreate">
          快速新建
        </el-button>
      </div>
    </div>

    <!-- KPI -->
    <el-row v-if="data" :gutter="8" class="kpi-row">
      <el-col v-for="k in kpiCards" :key="k.key" :xs="12" :sm="8" :md="3">
        <div class="kpi-card" :class="[k.cls, { 'kpi-clickable': k.clickable }]" @click="k.action && k.action()">
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
    <div v-if="bulkMode && selectedIds.length" class="batch-bar">
      <span>已选 {{ selectedIds.length }} 项</span>
      <el-select v-model="batchStatus" placeholder="批量改状态" size="small" style="width: 140px"
        @change="runBatch('status', batchStatus)">
        <el-option v-for="s in [TASK_STATUS.PENDING, TASK_STATUS.RUNNING, TASK_STATUS.DONE, TASK_STATUS.CANCELLED]" :key="s" :label="s" :value="s" />
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
      <div v-for="st in [TASK_STATUS.CONTRACT_REVIEW, TASK_STATUS.PENDING, TASK_STATUS.RUNNING, TASK_STATUS.REVIEWING, TASK_STATUS.DONE]" :key="st" class="board-col">
        <div class="col-head" :class="`col-${st}`">
          {{ st }}
          <span class="col-count">{{ data.status_groups?.[st]?.length || 0 }}</span>
        </div>
        <div class="col-body">
          <el-checkbox v-if="bulkMode && (data.status_groups?.[st] || []).length" class="col-check"
            :model-value="selectedIds.length > 0 && (data.status_groups?.[st] || []).every((t) => selectedIds.includes(t.id))"
            @change="(v: boolean | string | number | undefined) => toggleCol(st, !!v)">
            全选
          </el-checkbox>
          <div v-for="t in data.status_groups?.[st] || []" :key="t.id" class="task-card"
            :class="{ overdue: t.overdue, selected: selectedIds.includes(t.id), expanded: expandedId === t.id }">
            <div class="task-line" @click="openInline(t)">
              <el-checkbox v-if="bulkMode" class="task-check" :model-value="selectedIds.includes(t.id)"
                @click.stop @change="(v: boolean | string | number | undefined) => toggleSelect(t.id, !!v)" />
              <span class="status-dot" :class="`dot-${t.status}`" />
              <span class="task-title" :title="t.title">{{ t.title }}</span>
              <span class="task-badges">
                <span v-if="t.overdue" class="tag-badge tag-overdue">逾期</span>
                <span v-if="t.task_type === '突发'" class="tag-badge tag-urgent">突发</span>
                <span v-if="t.priority === '紧急'" class="tag-badge tag-urgent">紧急</span>
              </span>
            </div>
            <!-- 第二行：常态=负责人+时间；编辑态=负责人/状态下拉+时间只读 -->
            <div class="task-line2">
              <template v-if="expandedId === t.id">
                <el-select v-model="inlineForm.assignee_id" size="small" clearable filterable placeholder="负责人"
                  class="ie-select">
                  <el-option v-for="e in data?.engineers || []" :key="e.id" :label="e.name" :value="e.id" />
                </el-select>
                <el-select v-model="inlineForm.status" size="small" class="ie-select"
                  :disabled="t.status === TASK_STATUS.REVIEWING || t.status === TASK_STATUS.CONTRACT_REVIEW"
                  :placeholder="t.status === TASK_STATUS.CONTRACT_REVIEW ? '合同审批中' : t.status === TASK_STATUS.REVIEWING ? '待审核中' : '状态'">
                  <el-option v-for="s in [TASK_STATUS.PENDING, TASK_STATUS.RUNNING, TASK_STATUS.DONE, TASK_STATUS.CANCELLED]" :key="s" :label="s" :value="s" />
                </el-select>
              </template>
              <span v-else class="task-assignee">{{ t.assignee_name || '未指派' }}</span>
              <span class="task-range">{{ rangeText(t) }}</span>
            </div>
            <!-- 第三行：操作按钮（编辑态，均匀分布；删除贴右缘与时间右缘对齐） -->
            <div v-if="expandedId === t.id && t.status === TASK_STATUS.CONTRACT_REVIEW" class="contract-review-box">
              <span>例外原因：{{ t.contract_exception_reason || '-' }}</span>
            </div>
            <div v-if="expandedId === t.id" class="task-actions">
              <template v-if="t.status === TASK_STATUS.CONTRACT_REVIEW">
                <el-button v-if="canContractReview" size="small" type="success"
                  @click="reviewContract(t, true)">合同例外审核通过</el-button>
                <el-button v-if="canContractReview" size="small" type="danger"
                  @click="reviewContract(t, false)">拒绝</el-button>
                <el-button size="small" @click="cancelInline">取消</el-button>
              </template>
              <template v-else>
                <el-button size="small" type="primary" @click="saveInline">保存</el-button>
                <el-button size="small" type="warning" plain @click="openUpload">
                  {{ record ? '重新上传' : '上传' }}
                </el-button>
                <el-button size="small" @click="cancelInline">取消</el-button>
                <el-button size="small" type="danger" plain @click="onDelete(t)">删除</el-button>
              </template>
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
            :class="{ overdue: t.overdue, selected: selectedIds.includes(t.id), expanded: expandedId === t.id }">
            <div class="task-line" @click="openInline(t)">
              <el-checkbox v-if="bulkMode" class="task-check" :model-value="selectedIds.includes(t.id)"
                @click.stop @change="(v: boolean | string | number | undefined) => toggleSelect(t.id, !!v)" />
              <span class="status-dot" :class="`dot-${t.status}`" />
              <span class="task-title" :title="t.title">{{ t.title }}</span>
              <span class="task-badges">
                <span v-if="t.overdue" class="tag-badge tag-overdue">逾期</span>
                <span v-if="t.task_type === '突发'" class="tag-badge tag-urgent">突发</span>
                <span v-if="t.priority === '紧急'" class="tag-badge tag-urgent">紧急</span>
              </span>
            </div>
            <!-- 第二行：常态=负责人+时间；编辑态=负责人/状态下拉+时间只读 -->
            <div class="task-line2">
              <template v-if="expandedId === t.id">
                <el-select v-model="inlineForm.assignee_id" size="small" clearable filterable placeholder="负责人"
                  class="ie-select">
                  <el-option v-for="eng in data?.engineers || []" :key="eng.id" :label="eng.name" :value="eng.id" />
                </el-select>
                <el-select v-model="inlineForm.status" size="small" class="ie-select"
                  :disabled="t.status === TASK_STATUS.REVIEWING || t.status === TASK_STATUS.CONTRACT_REVIEW"
                  :placeholder="t.status === TASK_STATUS.CONTRACT_REVIEW ? '合同审批中' : t.status === TASK_STATUS.REVIEWING ? '待审核中' : '状态'">
                  <el-option v-for="s in [TASK_STATUS.PENDING, TASK_STATUS.RUNNING, TASK_STATUS.DONE, TASK_STATUS.CANCELLED]" :key="s" :label="s" :value="s" />
                </el-select>
              </template>
              <span v-else class="task-assignee">{{ t.assignee_name || '未指派' }}</span>
              <span class="task-range">{{ rangeText(t) }}</span>
            </div>
            <!-- 第三行：操作按钮（编辑态，均匀分布；删除贴右缘与时间右缘对齐） -->
            <div v-if="expandedId === t.id && t.status === TASK_STATUS.CONTRACT_REVIEW" class="contract-review-box">
              <span>例外原因：{{ t.contract_exception_reason || '-' }}</span>
            </div>
            <div v-if="expandedId === t.id" class="task-actions">
              <template v-if="t.status === TASK_STATUS.CONTRACT_REVIEW">
                <el-button v-if="canContractReview" size="small" type="success"
                  @click="reviewContract(t, true)">合同例外审核通过</el-button>
                <el-button v-if="canContractReview" size="small" type="danger"
                  @click="reviewContract(t, false)">拒绝</el-button>
                <el-button size="small" @click="cancelInline">取消</el-button>
              </template>
              <template v-else>
                <el-button size="small" type="primary" @click="saveInline">保存</el-button>
                <el-button size="small" type="warning" plain @click="openUpload">
                  {{ record ? '重新上传' : '上传' }}
                </el-button>
                <el-button size="small" @click="cancelInline">取消</el-button>
                <el-button size="small" type="danger" plain @click="onDelete(t)">删除</el-button>
              </template>
            </div>
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
        <el-form-item label="合同例外原因">
          <el-input v-model="createForm.contract_exception_reason" type="textarea" :rows="2"
            placeholder="客户合同已过期时必填，提交后由主管审核" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="createVisible = false">取消</el-button>
        <el-button type="primary" :loading="creating" @click="doCreate">创建</el-button>
      </template>
    </el-dialog>

    <!-- 现场报告预览弹窗 -->
    <el-dialog v-model="reportPreviewVisible" title="现场报告预览" width="900px" top="5vh" destroy-on-close>
      <div class="preview-body">
        <FilePreview v-if="reportPreviewUrl" :url="reportPreviewUrl" :file-name="reportPreviewName" />
      </div>
      <template #footer>
        <span class="preview-name">{{ reportPreviewName || '' }}</span>
        <el-button @click="reportPreviewVisible = false">关闭</el-button>
        <el-button type="primary" :icon="Download" @click="downloadLatestReport">下载文件</el-button>
      </template>
    </el-dialog>

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
import { ElMessageBox } from 'element-plus/es/components/message-box/index'
import type { UploadFile } from 'element-plus/es/components/upload'
import { ref, reactive, computed, onMounted } from 'vue'
import { Plus, Search, Download, Upload, UploadFilled, Delete } from '@element-plus/icons-vue'
import {
  fetchTaskSchedule, createTaskSchedule, updateTaskSchedule, deleteTaskSchedule,
  batchTaskSchedule, fetchImportTemplate, importTaskSchedule, downloadBase64,
  fetchRequiredAssets, reviewTaskContract,
  type TaskScheduleData, type TaskScheduleItem,
} from '@/api/taskSchedule'
import { fetchInspections, fetchInspection, fetchInspectionVersions, uploadTaskReport,
  versionReportUrl, type Inspection, type SubmissionVersion } from '@/api/inspections'
import FilePreview from '@/components/FilePreview.vue'
import { useUserStore } from '@/stores/user'
import { useUiStore } from '@/stores/ui'
import { TASK_STATUS, REVIEW_STATUS } from '@/utils/status'

const user = useUserStore()
const ui = useUiStore()
const data = ref<TaskScheduleData | null>(null)
const loading = ref(false)
const query = reactive<Record<string, unknown>>({ view: 'engineer', period: 'this_quarter', q: '', status: '' })
const onlyOverdue = ref(false)
const selectedIds = ref<number[]>([])
const batchStatus = ref('')
const batchAssignee = ref<number | null>(null)
const bulkMode = ref(false)

const createVisible = ref(false)
const creating = ref(false)
const createFormRef = ref()
const createForm = reactive<Record<string, unknown>>({
  title: '', customer_id: undefined, assignee_id: null, planned_start: '', planned_end: '',
  priority: '中', estimated_effort: null, task_type: '计划', remark: '', contract_exception_reason: '',
})

// 行内展开编辑（V29：点击卡片在卡片下方展开，状态/负责人快捷修改，不再弹窗）
const expandedId = ref<number | null>(null)
const inlineForm = reactive<{ status: string; assignee_id: number | null }>({ status: '', assignee_id: null })
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
  if (st === TASK_STATUS.REVIEWING) return '任务正在审核中，请等待审核结果后再上传'
  if (st === TASK_STATUS.DONE) return '任务已完成，可补传报告/资料（补传不改变任务状态）'
  if (st === TASK_STATUS.CANCELLED) return '任务已取消，不可上传'
  if (record.value?.review_status === REVIEW_STATUS.PENDING) return '已有报告在审核中，请等待审核结果'
  return ''
})
const canContractReview = computed(() =>
  user.hasPerm('contract:review') || user.isSupervisor)

const kpiCards = computed(() => {
  const k = data.value?.kpi
  if (!k) return []
  const statusCards = [
    { key: 'pending', label: TASK_STATUS.PENDING, value: k.pending, cls: 'warning', status: TASK_STATUS.PENDING },
    { key: 'running', label: TASK_STATUS.RUNNING, value: k.running, cls: 'primary', status: TASK_STATUS.RUNNING },
    { key: 'reviewing', label: TASK_STATUS.REVIEWING, value: k.reviewing, cls: 'info', status: TASK_STATUS.REVIEWING },
    { key: 'done', label: TASK_STATUS.DONE, value: k.done, cls: 'success', status: TASK_STATUS.DONE },
    { key: 'contract_review', label: TASK_STATUS.CONTRACT_REVIEW, value: k.contract_review,
      cls: 'danger', status: TASK_STATUS.CONTRACT_REVIEW },
  ]
  return [
    { key: 'total', label: '总任务', value: k.total, cls: '', clickable: true, action: clearFilters },
    ...statusCards.map((c) => ({ ...c, clickable: true, action: () => applyStatusFilter(c.status) })),
    { key: 'overdue', label: '逾期', value: k.overdue, cls: 'danger', clickable: true, action: applyOverdue },
    { key: 'est', label: '预估人天', value: k.est_effort, cls: '', clickable: false },
    { key: 'act', label: '实际人天', value: k.act_effort, cls: '', clickable: false },
  ]
})

// KPI 卡点击筛选：状态/逾期在当前页应用筛选，总任务清空
function applyStatusFilter(st: string) {
  query.status = st
  onlyOverdue.value = false
  query.view = 'status'
  reload()
}

function applyOverdue() {
  query.status = ''
  onlyOverdue.value = true
  reload()
}

function clearFilters() {
  query.status = ''
  onlyOverdue.value = false
  reload()
}

// 任务时间范围展示：2026-08-01 ~ 2026-08-31 → 8/1~8/31；跨年显示完整日期；仅结束显示「08-31 止」
function rangeText(t: TaskScheduleItem) {
  const s = t.planned_start || ''
  const e = t.planned_end || ''
  const short = (d: string) => {
    const [, m, day] = d.split('-')
    return `${Number(m)}/${Number(day)}`
  }
  if (s && e) return `${s.slice(0, 4) !== e.slice(0, 4) ? `${s.slice(5)}~${e.slice(5)}` : `${short(s)}~${short(e)}`}`
  if (s) return `${short(s)} 起`
  if (e) return `${short(e)} 止`
  return '未排期'
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

function toggleBulkMode() {
  bulkMode.value = !bulkMode.value
  if (!bulkMode.value) {
    selectedIds.value = []
    batchStatus.value = ''
    batchAssignee.value = null
  }
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
    priority: '中', estimated_effort: null, task_type: '计划', remark: '', contract_exception_reason: '',
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

function openInline(t: TaskScheduleItem) {
  // 再次点击当前展开卡片 → 收起；点击其他卡片 → 切换展开
  if (expandedId.value === t.id) {
    cancelInline()
    return
  }
  expandedId.value = t.id
  detail.value = t
  inlineForm.status = t.status
  inlineForm.assignee_id = t.assignee_id
  loadRecord()
}

function cancelInline() {
  expandedId.value = null
  detail.value = null
  record.value = null
  versions.value = []
}

async function saveInline() {
  if (!detail.value) return
  const patch: Record<string, unknown> = {}
  if (inlineForm.status !== detail.value.status) patch.status = inlineForm.status
  if (inlineForm.assignee_id !== detail.value.assignee_id) patch.assignee_id = inlineForm.assignee_id
  if (!Object.keys(patch).length) {
    ui.toast('无改动', 'info')
    return
  }
  try {
    await updateTaskSchedule(detail.value.id, patch)
    ui.toast('已保存', 'success')
    cancelInline()
    reload()
  } catch (e) {
    ui.toast((e as Error).message, 'error')
  }
}

async function reviewContract(task: TaskScheduleItem, approved: boolean) {
  try {
    await ElMessageBox.confirm(
      approved ? `确认通过「${task.title}」的合同例外申请？` : `确认拒绝「${task.title}」的合同例外申请？`,
      '合同例外审核', { type: approved ? 'warning' : 'error' })
  } catch { return }
  try {
    await reviewTaskContract(task.id, approved)
    ui.toast(approved ? '审核已通过' : '审核已拒绝', 'success')
    cancelInline()
    reload()
  } catch (e) {
    ui.toast((e as Error).message, 'error')
  }
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
    fetchRequiredAssets(detail.value.id)
      .then((data) => {
        requiredAssets.value = data.required_assets as unknown as Record<string, boolean>
        devices.value = data.devices
      })
      .catch(() => { /* toast */ })
  }
}

function downloadLatestReport() {
  const latest = versions.value.slice().reverse().find((v) => v.report_file)
  const rid = latest?.id ?? 0
  if (rid) window.open(versionReportUrl('inspection', rid), '_blank')
}

// ==================== 现场报告在线预览 ====================
const reportPreviewVisible = ref(false)
const reportPreviewUrl = ref('')
const reportPreviewName = ref('')

function previewLatestReport() {
  const latest = versions.value.slice().reverse().find((v) => v.report_file)
  if (!latest) return
  reportPreviewUrl.value = versionReportUrl('inspection', latest.id)
  reportPreviewName.value = latest.report_name || ''
  reportPreviewVisible.value = true
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

async function onDelete(t: TaskScheduleItem) {
  try {
    await ElMessageBox.confirm(`确定删除任务「${t.title}」吗？`, '删除确认', { type: 'warning' })
  } catch { return }
  deleting.value = true
  try {
    await deleteTaskSchedule(t.id)
    ui.toast('已删除', 'success')
    cancelInline()
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
.kpi-clickable {
  cursor: pointer;
  transition: border-color 0.15s, box-shadow 0.15s, transform 0.15s;
}
.kpi-clickable:hover {
  border-color: var(--itsm-primary);
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.08);
  transform: translateY(-1px);
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
  flex: 1; min-width: 310px; border: 1px solid var(--itsm-border); border-radius: 10px;
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
.upload-hint { color: var(--el-color-warning); font-size: 12px; }
.preview-body { min-height: 420px; }
.preview-name { float: left; font-size: 12px; color: var(--el-text-color-secondary); line-height: 32px; }
.mt-2 { margin-top: 8px; }
.asset-row { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; width: 100%; }
.asset-col { display: flex; flex-direction: column; gap: 8px; width: 100%; }
.asset-tip { font-size: 12px; color: var(--itsm-text-muted); }
.skip-box { display: inline-flex; }
.task-card {
  border: 1px solid var(--itsm-border); border-radius: 8px; padding: 8px 10px; margin-bottom: 8px;
  cursor: pointer; transition: border-color 0.15s;
}
.task-card:hover { border-color: var(--itsm-primary); }
.task-card.overdue { border-color: var(--el-color-danger); }
.task-card.selected { background: var(--el-color-primary-light-9); }
.task-card.expanded { border-color: var(--itsm-primary); box-shadow: 0 1px 6px rgba(0, 0, 0, 0.08); }
/* 第一行：checkbox 流内紧凑，左边不留空白 */
.task-line { display: flex; align-items: center; gap: 6px; min-width: 0; }
.task-check { margin: 0; }
.status-dot {
  width: 9px; height: 9px; border-radius: 50%; flex-shrink: 0; display: inline-block;
}
.dot-待执行 { background: var(--el-color-warning); }
.dot-执行中 { background: var(--el-color-primary); }
.dot-待审核 { background: var(--el-color-info); }
.dot-已完成 { background: var(--el-color-success); }
.dot-已取消 { background: var(--itsm-text-muted); }
.task-title {
  font-size: 13px; font-weight: 600; white-space: nowrap; overflow: hidden;
  text-overflow: ellipsis; min-width: 0; flex: 1;
}
.task-badges { display: flex; gap: 4px; flex-shrink: 0; }
.tag-badge {
  font-size: 11px; line-height: 1; padding: 2px 5px; border-radius: 3px; color: #fff;
}
.tag-overdue { background: var(--el-color-danger); }
.tag-urgent { background: var(--el-color-warning); }
/* 第二行：左缘=标题左缘(checkbox14+gap6+dot9+gap6=35px) */
.task-line2 {
  display: flex; justify-content: space-between; align-items: center; gap: 8px;
  margin-top: 3px; padding-left: 35px; font-size: 12px; color: var(--itsm-text-muted);
}
.task-assignee {
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis; min-width: 0;
}
.task-range { white-space: nowrap; margin-left: auto; }
/* 第二行编辑态：负责人/状态下拉 + 时间右置 */
.ie-select { width: 96px; }
/* 第三行：操作按钮从卡片左缘开始均匀分布（删除贴右缘=时间右缘），不超出边框 */
.task-actions {
  display: flex; justify-content: space-between; align-items: center; gap: 6px;
  margin-top: 8px; border-top: 1px dashed var(--itsm-border);
  padding-top: 8px; flex-wrap: nowrap;
}
</style>
