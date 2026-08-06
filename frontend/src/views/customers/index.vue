<template>
  <div class="page-container">
    <div class="page-header">
      <h2 class="page-title">客户管理</h2>
      <div class="header-actions">
        <el-button :icon="Download" plain @click="doExport">导出</el-button>
        <el-button v-if="user.hasPerm('customer:add')" :icon="Upload" plain @click="importVisible = true">导入</el-button>
        <el-button v-if="user.hasPerm('customer:add')" type="primary" :icon="Plus" @click="openCreate">
          新建客户
        </el-button>
      </div>
    </div>

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

    <!-- 列表 -->
    <DataTable
      ref="tableRef"
      :columns="columns"
      :fetch-data="fetchCustomers"
      :query="query"
      row-key="id"
      @row-click="openDetail"
    />

    <!-- 详情抽屉 -->
    <el-drawer v-model="detailVisible" :title="detail ? detail.name : ''" size="560px" destroy-on-close>
      <template v-if="detail">
        <el-divider content-position="left">基本信息</el-divider>
        <el-descriptions :column="2" border size="small">
          <el-descriptions-item label="等级">
            <el-tag size="small" :type="CUSTOMER_LEVEL_TAG[detail.level] || 'info'">
              {{ CUSTOMER_LEVEL_LABELS[detail.level] || detail.level }}
            </el-tag>
          </el-descriptions-item>
          <el-descriptions-item label="单位类别">{{ detail.category_name || '-' }}</el-descriptions-item>
          <el-descriptions-item label="所属地区">{{ detail.region_name || '-' }}</el-descriptions-item>
          <el-descriptions-item label="城市">{{ detail.city || '-' }}</el-descriptions-item>
          <el-descriptions-item label="联系人">{{ detail.contact_person || '-' }}</el-descriptions-item>
          <el-descriptions-item label="电话">{{ detail.phone || '-' }}</el-descriptions-item>
          <el-descriptions-item label="邮箱">{{ detail.email || '-' }}</el-descriptions-item>
          <el-descriptions-item label="来源">{{ detail.source || '-' }}</el-descriptions-item>
          <el-descriptions-item label="地址" :span="2">{{ detail.address || '-' }}</el-descriptions-item>
          <el-descriptions-item label="备注" :span="2">{{ detail.remark || '-' }}</el-descriptions-item>
        </el-descriptions>

        <el-divider content-position="left">驻场信息</el-divider>
        <el-descriptions :column="2" border size="small">
          <el-descriptions-item label="是否驻场">
            <el-tag size="small" :type="detail.has_onsite ? 'success' : 'info'">
              {{ detail.has_onsite ? '有' : '无' }}
            </el-tag>
          </el-descriptions-item>
          <el-descriptions-item label="攻防演练">
            <el-tag size="small" :type="detail.has_drill ? 'warning' : 'info'">
              {{ detail.has_drill ? '有' : '无' }}
            </el-tag>
          </el-descriptions-item>
          <el-descriptions-item label="驻场联系人">{{ detail.onsite_contact || '-' }}</el-descriptions-item>
          <el-descriptions-item label="驻场电话">{{ detail.onsite_phone || '-' }}</el-descriptions-item>
          <el-descriptions-item label="驻场办公室" :span="2">{{ detail.onsite_office || '-' }}</el-descriptions-item>
        </el-descriptions>

        <el-divider content-position="left">关联统计</el-divider>
        <el-descriptions :column="3" border size="small">
          <el-descriptions-item label="设备数">{{ detail.device_count ?? 0 }}</el-descriptions-item>
          <el-descriptions-item label="巡检数">{{ detail.inspection_count ?? 0 }}</el-descriptions-item>
          <el-descriptions-item label="工单数">{{ detail.ticket_count ?? 0 }}</el-descriptions-item>
        </el-descriptions>

        <template v-if="detail.extra_fields?.length">
          <el-divider content-position="left">自定义字段</el-divider>
          <el-descriptions :column="1" border size="small">
            <el-descriptions-item v-for="f in detail.extra_fields" :key="f.name" :label="f.name">
              {{ f.value || '-' }}
            </el-descriptions-item>
          </el-descriptions>
        </template>

        <div class="drawer-actions">
          <el-button v-if="user.hasPerm('customer:edit')" type="primary" @click="openEdit(detail)">编辑</el-button>
          <el-button @click="detailVisible = false">关闭</el-button>
        </div>
      </template>
    </el-drawer>

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
import { Plus, Search, Download, Upload, UploadFilled } from '@element-plus/icons-vue'
import { useRoute } from 'vue-router'
import DataTable, { type DataColumn } from '@/components/DataTable.vue'
import { useUserStore } from '@/stores/user'
import { useUiStore } from '@/stores/ui'
import {
  fetchCustomers, fetchCustomer, createCustomer, updateCustomer, deleteCustomer,
  fetchCustomerDicts, exportCustomers, importCustomers,
  CUSTOMER_LEVEL_TAG, CUSTOMER_LEVEL_LABELS,
  type Customer, type CustomerDicts, type CustomerForm, type RegionItem,
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

async function doExport() {
  try {
    const res = await exportCustomers()
    saveBase64(res.content, res.filename)
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
    tableRef.value?.refresh()
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
const tableRef = ref()

const columns = computed<DataColumn[]>(() => [
  { key: 'name', label: '客户名称', type: 'link', minWidth: 180, asTitle: true,
    link: (r) => `/app/customers/${r.id}` },
  { key: 'contact_person', label: '联系人', width: 100 },
  { key: 'phone', label: '电话', minWidth: 120 },
  { key: 'level', label: '等级', width: 80, type: 'tag', asTag: true,
    tagMap: CUSTOMER_LEVEL_TAG, valueMap: CUSTOMER_LEVEL_LABELS },
  { key: 'city', label: '城市', minWidth: 100 },
  { key: 'device_count', label: '设备数', width: 80 },
  { key: 'has_onsite_label', label: '驻场', width: 70 },
  { key: 'actions', label: '操作', width: 110, type: 'action', fixed: 'right',
    actions: [
      { label: '编辑', type: 'primary', link: true, perm: 'customer:edit', icon: 'Edit',
        onClick: (row) => openEdit(row as unknown as Customer) },
      { label: '删除', type: 'danger', link: true, perm: 'customer:delete', icon: 'Delete',
        onClick: (row) => onDelete(row as unknown as Customer) },
    ] },
])

// 详情
const detailVisible = ref(false)
const detail = ref<Customer | null>(null)

async function openDetail(row: Record<string, unknown>) {
  try {
    detail.value = await fetchCustomer(row.id as number)
    detailVisible.value = true
  } catch { /* toast */ }
}

// 支持 /app/customers/:id 直达（全局搜索跳转）
onMounted(() => {
  const id = Number(route.params.id)
  if (id && !Number.isNaN(id)) openDetail({ id })
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
    category_id: null, level: 'auto', address: '', regionPath: [],
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
  formVisible.value = true
}

function openEdit(c: Customer) {
  Object.assign(form, blankForm(), {
    id: c.id, name: c.name, contact_person: c.contact_person, phone: c.phone, email: c.email,
    category_id: c.category_id, level: c.level || '常规', address: c.address,
    regionPath: regionPathOf(c.region_id),
    has_onsite: c.has_onsite, onsite_contact: c.onsite_contact, onsite_phone: c.onsite_phone,
    onsite_office: c.onsite_office, has_drill: c.has_drill, remark: c.remark,
  })
  detailVisible.value = false
  formVisible.value = true
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
    }
    if (form.id) {
      await updateCustomer(form.id, payload)
      ui.toast('客户已更新', 'success')
    } else {
      await createCustomer(payload)
      ui.toast('客户已创建', 'success')
    }
    formVisible.value = false
    tableRef.value?.refresh()
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
    detailVisible.value = false
    tableRef.value?.refresh()
  } catch (e) {
    ui.toast((e as Error).message, 'error')
  }
}

function reload() { tableRef.value?.refresh() }

onMounted(() => {
  fetchCustomerDicts().then((d) => (dicts.value = d))
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
</style>
