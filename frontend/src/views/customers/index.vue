<template>
  <div class="page-container">
    <div class="page-header">
      <h2 class="page-title">客户管理</h2>
      <div class="header-actions">
        <el-button v-if="user.hasPerm('customer:export')" :icon="Download" plain @click="exportVisible = true">导出</el-button>
        <el-button v-if="user.hasPerm('customer:add')" :icon="Upload" plain @click="importVisible = true">导入</el-button>
        <el-button v-if="user.hasPerm('customer:add')" type="primary" :icon="Plus" @click="openCreate">
          新建客户
        </el-button>
      </div>
    </div>

    <!-- V24 导出筛选 -->
    <ExportDialog v-model="exportVisible" module="customer" title="导出客户"
      @submit="onExportSubmit" />

    <!-- 导入弹窗 -->
    <el-dialog v-model="importVisible" title="批量导入客户" width="520px" destroy-on-close>
      <el-alert type="info" :closable="false" class="mb-2" show-icon
        title="请先下载导入模板（Excel），按列填写后上传；已存在客户名自动跳过" />
      <div class="mb-2">
        <el-button size="small" link type="primary" @click="downloadTemplate">下载导入模板</el-button>
      </div>
      <el-upload ref="importUploadRef" drag :auto-upload="false" :limit="1" accept=".xlsx,.xls"
        :on-change="onImportFileChange" :on-remove="() => importFile = null">
        <el-icon class="el-icon--upload"><UploadFilled /></el-icon>
        <div class="el-upload__text">拖拽或点击选择 Excel 文件</div>
      </el-upload>
      <template #footer>
        <el-button @click="importVisible = false">取消</el-button>
        <el-button type="primary" :loading="importing" @click="doImport">开始导入</el-button>
      </template>
    </el-dialog>

    <!-- 筛选 -->
    <el-card shadow="never" class="filter-card">
      <div class="filter-row">
        <el-input v-model="query.search" placeholder="搜索名称 / 联系人 / 电话" clearable class="filter-search"
          @keyup.enter="reload" @clear="reload" />
        <el-select v-model="query.level" placeholder="等级" clearable class="filter-item" @change="reload">
          <el-option v-for="l in levels" :key="l" :label="CUSTOMER_LEVEL_LABELS[l] || l" :value="l" />
        </el-select>
        <el-select v-model="query.category_id" placeholder="单位类别" clearable class="filter-item" @change="reload">
          <el-option v-for="cat in categories" :key="cat.id" :label="cat.name" :value="cat.id" />
        </el-select>
        <el-button type="primary" plain :icon="Search" @click="reload">查询</el-button>
      </div>
    </el-card>

    <!-- 列表（按地区折叠：市 → 客户） -->
    <el-card shadow="never" v-loading="treeLoading">
      <GroupTree
        :nodes="tree"
        :leaf-depth="1"
        badge-key="customer_count"
        :default-expanded="hasFilter || !!route.params.id ? 2 : 0"
      >
        <template #leaf="{ node }">
          <div class="cust-leaf-wrap">
            <div class="tree-block cust-leaf" @click="toggleDetail(node as Customer)">
              <el-icon color="#2563eb"><Location /></el-icon>
              <span class="tree-name">{{ node.name }}</span>
              <span v-if="node.district" class="tree-district">{{ node.district }}</span>
              <el-tag size="small" :type="CUSTOMER_LEVEL_TAG[node.level] || 'info'" class="ml-2">
                {{ CUSTOMER_LEVEL_LABELS[node.level] || node.level }}
              </el-tag>
              <el-tag v-if="node.contract_status && node.contract_status !== '未设置合同'" size="small"
                :type="CONTRACT_STATUS_TAG[node.contract_status] || 'info'">
                {{ node.contract_status }}
              </el-tag>
              <el-tag v-if="(node.device_count ?? 0) > 0" size="small" type="info">
                设备 {{ node.device_count }}
              </el-tag>
              <span class="row-actions" @click.stop>
                <el-button v-if="user.hasPerm('customer:edit')" size="small" link type="primary"
                  @click="editFromRow(node as Customer)">编辑</el-button>
                <el-button v-if="user.hasPerm('customer:delete')" size="small" link type="danger"
                  @click="onDelete(node as Customer)">删除</el-button>
              </span>
            </div>

            <!-- 行内下展开详情 -->
            <div v-if="expandedId === (node as Customer).id" v-loading="detailLoading" class="cust-detail">
              <template v-if="detail">
                <!-- 编辑态：行内就地编辑（不弹窗），分组归类紧凑布局 -->
                <div v-if="editing" class="inline-edit">
                  <el-form ref="formRef" :model="form" :rules="formRules" label-width="88px" size="small">
                    <!-- 基本信息 -->
                    <el-divider content-position="left">基本信息</el-divider>
                    <el-row :gutter="12">
                      <el-col :xs="24" :sm="12">
                        <el-form-item label="客户名称" prop="name">
                          <el-input v-model="form.name" placeholder="必填" />
                        </el-form-item>
                      </el-col>
                      <el-col :xs="24" :sm="12">
                        <el-form-item label="等级">
                          <el-select v-model="form.level" class="w-full">
                            <el-option v-for="lv in levelOptions" :key="lv.value" :label="lv.label" :value="lv.value" />
                          </el-select>
                        </el-form-item>
                      </el-col>
                      <el-col :xs="24" :sm="12">
                        <el-form-item label="联系人">
                          <el-input v-model="form.contact_person" />
                        </el-form-item>
                      </el-col>
                      <el-col :xs="24" :sm="12">
                        <el-form-item label="电话">
                          <el-input v-model="form.phone" />
                        </el-form-item>
                      </el-col>
                      <el-col :xs="24" :sm="12">
                        <el-form-item label="邮箱">
                          <el-input v-model="form.email" />
                        </el-form-item>
                      </el-col>
                      <el-col :xs="24" :sm="12">
                        <el-form-item label="单位类别">
                          <el-select v-model="form.category_id" clearable class="w-full" placeholder="选择单位类别">
                            <el-option v-for="cat in categories" :key="cat.id" :label="cat.name" :value="cat.id" />
                          </el-select>
                        </el-form-item>
                      </el-col>
                      <el-col :xs="24" :sm="12">
                        <el-form-item label="所属地区">
                          <el-cascader v-model="form.regionPath" :options="regionOptions" clearable class="w-full"
                            placeholder="地市 → 区县" />
                        </el-form-item>
                      </el-col>
                      <el-col :xs="24" :sm="12">
                        <el-form-item label="地址">
                          <el-input v-model="form.address" />
                        </el-form-item>
                      </el-col>
                    </el-row>

                    <!-- 合同服务期 -->
                    <el-divider content-position="left">合同服务期</el-divider>
                    <el-row :gutter="12">
                      <el-col :xs="24" :sm="12">
                        <el-form-item label="合同开始">
                          <el-date-picker v-model="form.contract_start_date" type="date" value-format="YYYY-MM-DD"
                            class="w-full" placeholder="如 2026-01-01" />
                        </el-form-item>
                      </el-col>
                      <el-col :xs="24" :sm="12">
                        <el-form-item label="合同结束">
                          <el-date-picker v-model="form.contract_end_date" type="date" value-format="YYYY-MM-DD"
                            class="w-full" placeholder="如 2026-12-31" />
                        </el-form-item>
                      </el-col>
                      <el-col :xs="24" :sm="12">
                        <el-form-item label="办公室门牌">
                          <el-input v-model="form.office_room" placeholder="如 A栋 3F-301" />
                        </el-form-item>
                      </el-col>
                      <el-col :xs="24" :sm="12">
                        <el-form-item label="地图定位">
                          <el-input v-model="form.map_location" placeholder="经纬度或地图链接（外网工单可查看）" />
                        </el-form-item>
                      </el-col>
                    </el-row>

                    <!-- 驻场信息 -->
                    <el-divider content-position="left">驻场信息</el-divider>
                    <el-row :gutter="12">
                      <el-col :xs="24">
                        <el-form-item label="服务配置">
                          <el-checkbox v-model="form.has_onsite">有驻场</el-checkbox>
                          <el-checkbox v-model="form.has_drill">有攻防演练</el-checkbox>
                        </el-form-item>
                      </el-col>
                      <template v-if="form.has_onsite">
                        <el-col :xs="24" :sm="12">
                          <el-form-item label="驻场联系人">
                            <el-input v-model="form.onsite_contact" />
                          </el-form-item>
                        </el-col>
                        <el-col :xs="24" :sm="12">
                          <el-form-item label="驻场电话">
                            <el-input v-model="form.onsite_phone" />
                          </el-form-item>
                        </el-col>
                        <el-col :xs="24" :sm="12">
                          <el-form-item label="驻场办公室">
                            <el-input v-model="form.onsite_office" />
                          </el-form-item>
                        </el-col>
                      </template>
                    </el-row>

                    <!-- 备注 -->
                    <el-divider content-position="left">备注</el-divider>
                    <el-row :gutter="12">
                      <el-col :xs="24">
                        <el-form-item label="备注">
                          <el-input v-model="form.remark" type="textarea" :rows="2" />
                        </el-form-item>
                      </el-col>
                    </el-row>
                  </el-form>
                  <div class="drawer-actions">
                    <el-button type="primary" size="small" :loading="saving" @click="save">保存</el-button>
                    <el-button size="small" @click="cancelEdit">取消</el-button>
                  </div>
                </div>

                <!-- 展示态：3 列紧凑网格 -->
                <template v-else>
                <div class="detail-grid">
                  <div v-for="row in detailRows" :key="row.key" class="detail-cell">
                    <span class="cell-label">{{ row.label }}</span>
                    <span class="cell-value">
                      <el-tag v-if="row.key === 'level'" size="small"
                        :type="CUSTOMER_LEVEL_TAG[detail.level] || 'info'">
                        {{ CUSTOMER_LEVEL_LABELS[detail.level] || detail.level }}
                      </el-tag>
                      <template v-else-if="row.key === 'contract_status'">
                        <el-tag size="small" :type="CONTRACT_STATUS_TAG[detail.contract_status] || 'info'">
                          {{ detail.contract_status }}
                        </el-tag>
                        <span v-if="detail.contract_remaining_days != null" class="ml-2 text-muted">
                          {{ detail.contract_remaining_days < 0 ? `已过期 ${-detail.contract_remaining_days} 天` : `剩 ${detail.contract_remaining_days} 天` }}
                        </span>
                      </template>
                      <el-tag v-else-if="row.key === 'onsite'" size="small"
                        :type="detail.has_onsite ? 'success' : 'info'">{{ row.value }}</el-tag>
                      <el-tag v-else-if="row.key === 'drill'" size="small"
                        :type="detail.has_drill ? 'warning' : 'info'">{{ row.value }}</el-tag>
                      <span v-else>{{ row.value }}</span>
                    </span>
                  </div>
                </div>

                <div class="drawer-actions">
                  <el-button v-if="user.hasPerm('customer:edit')" type="primary" size="small"
                    @click="startEdit">编辑</el-button>
                  <el-button size="small" @click="collapseDetail">收起</el-button>
                </div>
                </template>
              </template>
            </div>
          </div>
        </template>
      </GroupTree>
      <el-empty v-if="!treeLoading && !tree.length" description="暂无客户" :image-size="60" />
    </el-card>

    <!-- 新建/编辑弹窗 -->
    <el-dialog v-model="formVisible" :title="form.id ? '编辑客户' : '新建客户'" width="720px" top="5vh" destroy-on-close>
      <el-form ref="formRef" :model="form" :rules="formRules" label-width="110px" size="default">
        <el-row :gutter="16">
          <el-col :xs="24" :sm="12">
            <el-form-item label="客户名称" prop="name">
              <el-input v-model="form.name" placeholder="必填" />
            </el-form-item>
          </el-col>
          <el-col :xs="24" :sm="12">
            <el-form-item label="等级">
              <el-select v-model="form.level" class="w-full">
                <el-option v-for="lv in levelOptions" :key="lv.value" :label="lv.label" :value="lv.value" />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :xs="24" :sm="12">
            <el-form-item label="联系人">
              <el-input v-model="form.contact_person" />
            </el-form-item>
          </el-col>
          <el-col :xs="24" :sm="12">
            <el-form-item label="电话">
              <el-input v-model="form.phone" />
            </el-form-item>
          </el-col>
          <el-col :xs="24" :sm="12">
            <el-form-item label="邮箱">
              <el-input v-model="form.email" />
            </el-form-item>
          </el-col>
          <el-col :xs="24" :sm="12">
            <el-form-item label="单位类别">
              <el-select v-model="form.category_id" clearable class="w-full" placeholder="选择单位类别">
                <el-option v-for="cat in categories" :key="cat.id" :label="cat.name" :value="cat.id" />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :xs="24">
            <el-form-item label="所属地区">
              <el-cascader v-model="form.regionPath" :options="regionOptions" clearable class="w-full"
                placeholder="地市 → 区县" />
            </el-form-item>
          </el-col>
          <el-col :xs="24">
            <el-form-item label="地址">
              <el-input v-model="form.address" />
            </el-form-item>
          </el-col>
          <el-col :xs="24" :sm="12">
            <el-form-item label="合同开始日期">
              <el-date-picker v-model="form.contract_start_date" type="date" value-format="YYYY-MM-DD"
                class="w-full" placeholder="如 2026-01-01" />
            </el-form-item>
          </el-col>
          <el-col :xs="24" :sm="12">
            <el-form-item label="合同结束日期">
              <el-date-picker v-model="form.contract_end_date" type="date" value-format="YYYY-MM-DD"
                class="w-full" placeholder="如 2026-12-31" />
            </el-form-item>
          </el-col>
          <el-col :xs="24" :sm="12">
            <el-form-item label="办公室门牌号">
              <el-input v-model="form.office_room" placeholder="如 A栋 3F-301" />
            </el-form-item>
          </el-col>
          <el-col :xs="24" :sm="12">
            <el-form-item label="地图定位">
              <el-input v-model="form.map_location" placeholder="经纬度或地图链接（外网工单可查看）" />
            </el-form-item>
          </el-col>
          <el-col :xs="24">
            <el-form-item label="驻场信息">
              <el-checkbox v-model="form.has_onsite">有驻场</el-checkbox>
            </el-form-item>
          </el-col>
          <template v-if="form.has_onsite">
            <el-col :xs="24" :sm="12">
              <el-form-item label="驻场联系人">
                <el-input v-model="form.onsite_contact" />
              </el-form-item>
            </el-col>
            <el-col :xs="24" :sm="12">
              <el-form-item label="驻场电话">
                <el-input v-model="form.onsite_phone" />
              </el-form-item>
            </el-col>
            <el-col :xs="24" :sm="12">
              <el-form-item label="驻场办公室">
                <el-input v-model="form.onsite_office" />
              </el-form-item>
            </el-col>
          </template>
          <el-col :xs="24">
            <el-form-item label="攻防演练">
              <el-checkbox v-model="form.has_drill">有攻防演练</el-checkbox>
            </el-form-item>
          </el-col>
          <el-col :xs="24">
            <el-form-item label="备注">
              <el-input v-model="form.remark" type="textarea" :rows="2" />
            </el-form-item>
          </el-col>
        </el-row>
      </el-form>
      <template #footer>
        <el-button @click="formVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="save">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ElMessageBox } from 'element-plus/es/components/message-box/index'
import type { UploadFile } from 'element-plus/es/components/upload'
import { ref, reactive, computed, onMounted } from 'vue'
import { Plus, Search, Download, Upload, UploadFilled, Location } from '@element-plus/icons-vue'
import { useRoute } from 'vue-router'
import GroupTree from '@/components/GroupTree.vue'
import ExportDialog from '@/components/ExportDialog.vue'
import { useUserStore } from '@/stores/user'
import { useUiStore } from '@/stores/ui'
import { handleExportResult } from '@/utils/export'
import {
  fetchCustomer, createCustomer, updateCustomer, deleteCustomer,
  fetchCustomerDicts, fetchCustomerTree, exportCustomers, importCustomers,
  CUSTOMER_LEVEL_TAG, CUSTOMER_LEVEL_LABELS, CONTRACT_STATUS_TAG,
  type Customer, type CustomerDicts, type CustomerForm, type CustomerTreeGroup, type RegionItem,
} from '@/api/customers'

const route = useRoute()
const user = useUserStore()
const ui = useUiStore()

// ==================== 导入 / 导出 ====================
const importVisible = ref(false)
const importing = ref(false)
const importUploadRef = ref()
const importFile = ref<File | null>(null)

function onImportFileChange(f: UploadFile) {
  importFile.value = f.raw ?? null
}

function downloadTemplate() {
  window.open('/exports/download-template/customer', '_blank')
}

// V24 导出筛选：列选择 + 创建时间范围
const exportVisible = ref(false)

async function onExportSubmit(payload: Record<string, unknown>) {
  try {
    const res = await exportCustomers({
      columns: payload.columns,
      date_from: payload.date_from || undefined,
      date_to: payload.date_to || undefined,
    })
    handleExportResult(res, { close: () => { exportVisible.value = false } })
    ui.toast('导出成功', 'success')
  } catch (e) {
    ui.toast((e as Error).message, 'error')
  }
}

async function doImport() {
  if (!importFile.value) {
    ui.toast('请选择 Excel 文件', 'warning')
    return
  }
  importing.value = true
  try {
    const fd = new FormData()
    fd.append('import_file', importFile.value)
    const res = await importCustomers(fd)
    let msg = `导入完成：成功 ${res.created} 条`
    if (res.unknown_categories.length) {
      msg += `；未识别单位类别（已留空）：${res.unknown_categories.join('、')}`
    }
    ui.toast(msg, res.unknown_categories.length ? 'warning' : 'success')
    importVisible.value = false
    loadTree()
  } catch (e) {
    ui.toast((e as Error).message, 'error')
  } finally {
    importing.value = false
  }
}
const dicts = ref<CustomerDicts | null>(null)

const categories = computed(() => dicts.value?.customer_categories || [])
const levels = computed(() => dicts.value?.levels || [])
const levelOptions = [
  { value: 'auto', label: '自动' },
  { value: '核心', label: '核心' },
  { value: '重点', label: '重点' },
  { value: '常规', label: '常规' },
]

const regionOptions = computed(() => {
  const regions = dicts.value?.regions || []
  return regions
    .filter((r: RegionItem) => !r.parent_id)
    .map((city: RegionItem) => ({
      value: city.id,
      label: city.name,
      children: regions.filter((r: RegionItem) => r.parent_id === city.id)
        .map((d: RegionItem) => ({ value: d.id, label: d.name })),
    }))
})

const query = reactive<Record<string, unknown>>({ search: '', level: '', category_id: undefined })

// ==================== 地区折叠树 ====================
const tree = ref<CustomerTreeGroup[]>([])
const treeLoading = ref(false)
const hasFilter = computed(() =>
  Boolean(query.search || query.level || query.category_id))

async function loadTree() {
  treeLoading.value = true
  try {
    const res = await fetchCustomerTree({
      search: query.search as string || undefined,
      level: query.level as string || undefined,
      category_id: query.category_id as number | undefined,
    })
    tree.value = res.tree
  } catch (e) {
    ui.toast((e as Error).message, 'error')
  } finally {
    treeLoading.value = false
  }
}

// 详情（行内下展开）
const expandedId = ref<number | null>(null)
const detailLoading = ref(false)
const detail = ref<Customer | null>(null)
// 行内就地编辑：详情展开后点「编辑」直接切换为行内表单（不弹窗）
const editing = ref(false)

async function toggleDetail(row: { id: number }) {
  if (expandedId.value === row.id) {
    collapseDetail()
    return
  }
  expandedId.value = row.id
  editing.value = false   // 展开其他客户 → 默认展示态
  detailLoading.value = true
  try {
    detail.value = await fetchCustomer(row.id)
  } catch { /* toast */ } finally {
    detailLoading.value = false
  }
}

function collapseDetail() {
  expandedId.value = null
  detail.value = null
  editing.value = false
}

/** 展示态明细行（字段名|值 单列表格，紧凑整齐） */
const detailRows = computed(() => {
  const d = detail.value
  if (!d) return []
  const val = (v: unknown) => (v === null || v === undefined || v === '' ? '-' : String(v))
  const rows: Array<{ key: string; label: string; value: string }> = [
    { key: 'name', label: '客户名称', value: val(d.name) },
    { key: 'level', label: '等级', value: val(d.level) },
    { key: 'category', label: '单位类别', value: val(d.category_name) },
    { key: 'region', label: '所属地区', value: val(d.region_name) },
    { key: 'city', label: '城市', value: val(d.city) },
    { key: 'contact', label: '联系人', value: val(d.contact_person) },
    { key: 'phone', label: '电话', value: val(d.phone) },
    { key: 'email', label: '邮箱', value: val(d.email) },
    { key: 'source', label: '来源', value: val(d.source) },
    { key: 'address', label: '地址', value: val(d.address) },
    { key: 'remark', label: '备注', value: val(d.remark) },
    { key: 'contract_period', label: '合同起止',
      value: `${val(d.contract_start_date)} ~ ${val(d.contract_end_date)}` },
    { key: 'contract_status', label: '合同状态', value: val(d.contract_status) },
    { key: 'office_room', label: '办公室门牌号', value: val(d.office_room) },
    { key: 'map_location', label: '地图定位', value: val(d.map_location) },
    { key: 'onsite', label: '是否驻场', value: d.has_onsite ? '有' : '无' },
    { key: 'drill', label: '攻防演练', value: d.has_drill ? '有' : '无' },
    { key: 'onsite_contact', label: '驻场联系人', value: val(d.onsite_contact) },
    { key: 'onsite_phone', label: '驻场电话', value: val(d.onsite_phone) },
    { key: 'onsite_office', label: '驻场办公室', value: val(d.onsite_office) },
    { key: 'device_count', label: '设备数', value: String(d.device_count ?? 0) },
    { key: 'inspection_count', label: '巡检数', value: String(d.inspection_count ?? 0) },
    { key: 'ticket_count', label: '工单数', value: String(d.ticket_count ?? 0) },
  ]
  for (const f of d.extra_fields || []) {
    if (f?.name) rows.push({ key: `extra_${f.name}`, label: f.name, value: val(f.value) })
  }
  return rows
})

// 支持 /app/customers/:id 直达（全局搜索跳转）
onMounted(() => {
  const id = Number(route.params.id)
  if (id && !Number.isNaN(id)) toggleDetail({ id })
})

// 表单
interface CustomerFormModel {
  id?: number
  name: string
  contact_person: string
  phone: string
  email: string
  category_id: number | null
  level: string
  address: string
  contract_start_date: string
  contract_end_date: string
  office_room: string
  map_location: string
  regionPath: number[]
  has_onsite: boolean
  onsite_contact: string
  onsite_phone: string
  onsite_office: string
  has_drill: boolean
  remark: string
}

const formVisible = ref(false)
const saving = ref(false)
const formRef = ref()
const form = reactive<CustomerFormModel>(blankForm())

function blankForm(): CustomerFormModel {
  return {
    id: undefined, name: '', contact_person: '', phone: '', email: '',
    category_id: null, level: 'auto', address: '', contract_start_date: '',
    contract_end_date: '', office_room: '', map_location: '', regionPath: [],
    has_onsite: false, onsite_contact: '', onsite_phone: '', onsite_office: '',
    has_drill: false, remark: '',
  }
}

const formRules = { name: [{ required: true, message: '请输入客户名称', trigger: 'blur' }] }

function regionPathOf(regionId: number | null | undefined): number[] {
  if (!regionId) return []
  const r = dicts.value?.regions.find((x: RegionItem) => x.id === regionId)
  if (!r) return []
  return r.parent_id ? [r.parent_id, r.id] : [r.id]
}

function openCreate() {
  Object.assign(form, blankForm())
  editing.value = false
  formVisible.value = true
}

/** 行内就地编辑：用已展开的详情填充表单，切换到编辑态（不再弹窗） */
function startEdit() {
  const c = detail.value
  if (!c) return
  Object.assign(form, blankForm(), {
    id: c.id, name: c.name, contact_person: c.contact_person, phone: c.phone, email: c.email,
    category_id: c.category_id, level: c.level || '常规', address: c.address,
    contract_start_date: c.contract_start_date || '', contract_end_date: c.contract_end_date || '',
    office_room: c.office_room || '', map_location: c.map_location || '',
    regionPath: regionPathOf(c.region_id),
    has_onsite: c.has_onsite, onsite_contact: c.onsite_contact, onsite_phone: c.onsite_phone,
    onsite_office: c.onsite_office, has_drill: c.has_drill, remark: c.remark,
  })
  editing.value = true
}

/** 树节点行直接点「编辑」：先展开详情再进入行内编辑态 */
async function editFromRow(c: Customer) {
  if (expandedId.value !== c.id) {
    await toggleDetail({ id: c.id })
  }
  if (detail.value) startEdit()
}

/** 取消行内编辑：切回展示态，不保存 */
function cancelEdit() {
  editing.value = false
}

async function save() {
  try { await formRef.value?.validate() } catch { return }
  saving.value = true
  try {
    const path = form.regionPath
    const payload: CustomerForm = {
      name: form.name, contact_person: form.contact_person, phone: form.phone,
      email: form.email, category_id: form.category_id, level: form.level,
      region_id: path.length ? path[path.length - 1] : null,
      address: form.address, has_onsite: form.has_onsite,
      onsite_contact: form.onsite_contact, onsite_phone: form.onsite_phone,
      onsite_office: form.onsite_office, has_drill: form.has_drill, remark: form.remark,
      contract_start_date: form.contract_start_date || undefined,
      contract_end_date: form.contract_end_date || undefined,
      office_room: form.office_room, map_location: form.map_location,
    }
    if (form.id) {
      await updateCustomer(form.id, payload)
      ui.toast('客户已更新', 'success')
    } else {
      await createCustomer(payload)
      ui.toast('客户已创建', 'success')
    }
    formVisible.value = false
    // 行内编辑保存：切回展示态并刷新详情（保持展开，数值最新）
    if (form.id && editing.value) {
      editing.value = false
      try {
        detail.value = await fetchCustomer(form.id)
      } catch { /* toast */ }
    }
    loadTree()
  } catch (e) {
    ui.toast((e as Error).message, 'error')
  } finally {
    saving.value = false
  }
}

async function onDelete(c: Customer) {
  try {
    await ElMessageBox.confirm(`确定删除客户「${c.name}」吗？`, '删除确认', { type: 'warning' })
  } catch { return }
  try {
    await deleteCustomer(c.id)
    ui.toast('已删除', 'success')
    if (expandedId.value === c.id) collapseDetail()
    loadTree()
  } catch (e) {
    ui.toast((e as Error).message, 'error')
  }
}

function reload() { loadTree() }

onMounted(() => {
  fetchCustomerDicts().then((d) => (dicts.value = d))
  loadTree()
})
</script>

<style scoped>
.filter-card { margin-bottom: 12px; }
.filter-row { display: flex; gap: 8px; flex-wrap: wrap; align-items: center; }
.filter-search { width: 220px; max-width: 100%; }
.filter-item { width: 140px; max-width: 100%; }
.header-actions { display: flex; gap: 8px; flex-wrap: wrap; }
.w-full { width: 100%; }
.drawer-actions { display: flex; gap: 8px; justify-content: flex-end; margin-top: 16px; }
.cust-leaf-wrap { margin-bottom: 8px; }
.cust-leaf {
  display: flex; align-items: center; gap: 8px; padding: 9px 12px;
  font-size: 13px; cursor: pointer; border: 1px solid var(--itsm-border);
  border-radius: 8px; margin-bottom: 8px;
}
.cust-leaf:hover { background: var(--el-fill-color-light); }
.cust-detail {
  border: 1px solid var(--itsm-border);
  border-top: 2px solid var(--el-color-primary);
  border-radius: 8px;
  padding: 12px;
  margin-bottom: 8px;
  background: var(--itsm-card-bg);
  min-height: 60px;
}
.inline-edit { padding: 4px 0; }
.inline-edit :deep(.el-form-item) { margin-bottom: 10px; }
/* 详情展示态：3 列紧凑网格 */
.detail-grid {
  display: grid; grid-template-columns: repeat(3, 1fr); gap: 6px 18px;
}
.detail-cell { min-width: 0; line-height: 1.7; }
.cell-label { color: var(--itsm-text-muted); font-size: 12px; margin-right: 6px; }
.cell-value { font-size: 13px; word-break: break-all; }
@media (max-width: 767px) {
  .detail-grid { grid-template-columns: repeat(2, 1fr); }
}
.ml-2 { margin-left: 4px; }
.tree-name { font-weight: 600; flex-shrink: 0; }
.tree-district { font-size: 12px; color: var(--itsm-text-muted); font-weight: 400; }
</style>
