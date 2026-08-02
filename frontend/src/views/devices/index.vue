<template>
  <div class="page-container">
    <div class="page-header">
      <h2 class="page-title">设备管理</h2>
      <div class="header-actions">
        <el-button v-if="user.hasPerm('device:add')" type="primary" :icon="Plus" @click="openCreate">
          新增设备
        </el-button>
      </div>
    </div>

    <!-- 筛选栏 -->
    <el-card shadow="never" class="filter-card">
      <div class="filter-row">
        <el-input
          v-model="query.search"
          placeholder="搜索名称 / IP / 品牌"
          clearable
          class="filter-search"
          @keyup.enter="reload"
          @clear="reload"
        />
        <el-select v-model="query.brand" placeholder="品牌" clearable class="filter-item" @change="reload">
          <el-option v-for="b in brands" :key="b" :label="b" :value="b" />
        </el-select>
        <el-select v-model="query.device_type" placeholder="类型" clearable class="filter-item" @change="reload">
          <el-option v-for="t in deviceTypes" :key="t.name" :label="t.name" :value="t.name" />
        </el-select>
        <el-select v-model="query.customer_id" placeholder="客户" clearable filterable class="filter-item" @change="reload">
          <el-option v-for="c in customers" :key="c.id" :label="c.name" :value="c.id" />
        </el-select>
        <el-button type="primary" plain :icon="Search" @click="reload">查询</el-button>
      </div>
    </el-card>

    <!-- 列表 -->
    <DataTable
      ref="tableRef"
      :columns="columns"
      :fetch-data="fetchDevices"
      :query="query"
      row-key="id"
      @row-click="openDetail"
    />

    <!-- 详情弹窗 -->
    <el-dialog v-model="detailVisible" :title="detail?.device_name || '设备详情'" width="680px">
      <el-descriptions v-if="detail" :column="2" border size="small">
        <el-descriptions-item label="客户">{{ detail.customer_name || '-' }}</el-descriptions-item>
        <el-descriptions-item label="类型">{{ detail.device_type || '-' }}</el-descriptions-item>
        <el-descriptions-item label="品牌/型号">{{ detail.brand }} {{ detail.model }}</el-descriptions-item>
        <el-descriptions-item label="序列号">{{ detail.serial_number || '-' }}</el-descriptions-item>
        <el-descriptions-item label="IP:端口">
          <code>{{ detail.ip_address }}:{{ detail.port }}</code>
        </el-descriptions-item>
        <el-descriptions-item label="登录">
          {{ detail.username || '-' }} / {{ detail.login_method || '-' }}
        </el-descriptions-item>
        <el-descriptions-item label="系统版本">{{ detail.os_version || '-' }}</el-descriptions-item>
        <el-descriptions-item label="规则库版本">{{ detail.rule_version || '-' }}</el-descriptions-item>
        <el-descriptions-item label="安装位置">{{ detail.location || '-' }}</el-descriptions-item>
        <el-descriptions-item label="授权">
          {{ detail.license_expiry || '-' }}
          <el-tag v-if="detail.license_remaining_days != null" size="small"
            :type="detail.license_remaining_days < 0 ? 'danger' : 'warning'" class="ml-1">
            {{ detail.license_remaining_days < 0 ? `过期 ${-detail.license_remaining_days} 天` : `剩 ${detail.license_remaining_days} 天` }}
          </el-tag>
        </el-descriptions-item>
        <el-descriptions-item label="在用">
          <el-tag size="small" :type="detail.is_in_use ? 'success' : 'info'">
            {{ detail.is_in_use ? '在用' : '停用' }}
          </el-tag>
        </el-descriptions-item>
        <el-descriptions-item label="备注" :span="2">{{ detail.remark || '-' }}</el-descriptions-item>
      </el-descriptions>
      <template #footer>
        <el-button v-if="user.hasPerm('device:reveal') && detail?.has_password" @click="revealPwd">
          <el-icon class="mr-1"><View /></el-icon>{{ pwdVisible ? '隐藏密码' : '查看密码' }}
        </el-button>
        <el-button v-if="user.hasPerm('device:edit')" type="primary" @click="openEdit(detail!)">编辑</el-button>
        <el-button @click="detailVisible = false">关闭</el-button>
      </template>
    </el-dialog>

    <!-- 新增/编辑弹窗 -->
    <el-dialog
      v-model="formVisible"
      :title="form.id ? '编辑设备' : '新增设备'"
      width="720px"
      top="4vh"
      destroy-on-close
    >
      <el-form ref="formRef" :model="form" :rules="formRules" label-width="110px" size="default">
        <el-row :gutter="16">
          <el-col :xs="24" :sm="12">
            <el-form-item label="设备名称" prop="device_name">
              <el-input v-model="form.device_name" placeholder="必填" />
            </el-form-item>
          </el-col>
          <el-col :xs="24" :sm="12">
            <el-form-item label="所属客户">
              <el-select v-model="form.customer_id" filterable clearable class="w-full">
                <el-option v-for="c in customers" :key="c.id" :label="c.name" :value="c.id" />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :xs="24" :sm="12">
            <el-form-item label="设备类型">
              <el-select v-model="form.device_type" filterable allow-create clearable class="w-full">
                <el-option v-for="t in deviceTypes" :key="t.name" :label="t.name" :value="t.name" />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :xs="24" :sm="12">
            <el-form-item label="品牌/型号">
              <div class="flex-gap">
                <el-input v-model="form.brand" placeholder="品牌" />
                <el-input v-model="form.model" placeholder="型号" />
              </div>
            </el-form-item>
          </el-col>
          <el-col :xs="24" :sm="12">
            <el-form-item label="IP地址">
              <el-input v-model="form.ip_address" placeholder="如 192.168.1.1" />
            </el-form-item>
          </el-col>
          <el-col :xs="24" :sm="12">
            <el-form-item label="端口">
              <el-input-number v-model="form.port" :min="1" :max="65535" />
            </el-form-item>
          </el-col>
          <el-col :xs="24" :sm="12">
            <el-form-item label="序列号">
              <el-input v-model="form.serial_number" />
            </el-form-item>
          </el-col>
          <el-col :xs="24" :sm="12">
            <el-form-item label="登录方式">
              <el-select v-model="form.login_method" allow-create clearable class="w-full">
                <el-option label="SSH" value="SSH" />
                <el-option label="Telnet" value="Telnet" />
                <el-option label="Web" value="Web" />
                <el-option label="SNMP" value="SNMP" />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :xs="24" :sm="12">
            <el-form-item label="用户名">
              <el-input v-model="form.username" />
            </el-form-item>
          </el-col>
          <el-col :xs="24" :sm="12">
            <el-form-item :label="form.id ? '新密码' : '密码'">
              <el-input v-model="form.password" type="password" show-password
                :placeholder="form.id ? '留空则不修改' : ''" />
            </el-form-item>
          </el-col>
          <el-col :xs="24" :sm="12">
            <el-form-item label="安装位置">
              <el-input v-model="form.location" />
            </el-form-item>
          </el-col>
          <el-col :xs="24" :sm="12">
            <el-form-item label="接口">
              <el-select v-model="form.interface" multiple filterable allow-create default-first-option
                class="w-full" placeholder="如 GigabitEthernet0/0/1" />
            </el-form-item>
          </el-col>
          <el-col :xs="24" :sm="12">
            <el-form-item label="系统版本">
              <el-input v-model="form.os_version" />
            </el-form-item>
          </el-col>
          <el-col :xs="24" :sm="12">
            <el-form-item label="规则库版本">
              <el-input v-model="form.rule_version" />
            </el-form-item>
          </el-col>
          <el-col :xs="24" :sm="12">
            <el-form-item label="授权开始">
              <el-date-picker v-model="form.license_start" type="date" value-format="YYYY-MM-DD"
                class="w-full" placeholder="开始日期" />
            </el-form-item>
          </el-col>
          <el-col :xs="24" :sm="12">
            <el-form-item label="授权截止">
              <el-date-picker v-model="form.license_expiry" type="date" value-format="YYYY-MM-DD"
                class="w-full" placeholder="截止日期" />
            </el-form-item>
          </el-col>
          <el-col :xs="24">
            <el-form-item label="备注">
              <el-input v-model="form.remark" type="textarea" :rows="2" />
            </el-form-item>
          </el-col>
          <el-col :xs="24">
            <el-form-item label="状态">
              <el-checkbox v-model="form.is_in_use">在用</el-checkbox>
              <el-checkbox v-model="form.is_maintenance">有过维修</el-checkbox>
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
import { ref, reactive, computed } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Plus, Search, View } from '@element-plus/icons-vue'
import DataTable, { type DataColumn } from '@/components/DataTable.vue'
import { useUserStore } from '@/stores/user'
import { useUiStore } from '@/stores/ui'
import {
  fetchDevices, fetchDevice, createDevice, updateDevice, deleteDevice, revealPassword,
  type Device, type DeviceForm,
} from '@/api/devices'

const user = useUserStore()
const ui = useUiStore()

// 筛选 + 字典数据
const query = reactive<Record<string, unknown>>({ search: '', brand: '', device_type: '', customer_id: undefined })
const brands = ref<string[]>([])
const deviceTypes = ref<{ name: string }[]>([])
const customers = ref<{ id: number; name: string }[]>([])

const tableRef = ref()

const columns = computed<DataColumn[]>(() => [
  { key: 'device_name', label: '设备名称', type: 'link', minWidth: 160, asTitle: true,
    link: (r) => `/app/devices/${r.id}` },
  { key: 'device_type', label: '类型', width: 90 },
  { key: 'customer_name', label: '客户', minWidth: 100 },
  { key: 'brand', label: '品牌/型号', minWidth: 130,
    cellClass: () => 'cell-muted' },
  { key: 'ip_address', label: 'IP:端口', minWidth: 130 },
  { key: 'os_version', label: '系统版本', minWidth: 110 },
  { key: 'is_in_use', label: '状态', width: 80, type: 'tag', asTag: true,
    tagMap: { 'true': 'success', 'false': 'info' } },
  { key: 'license_remaining_days', label: '授权', minWidth: 110,
    cellClass: (r) => {
      const d = r.license_remaining_days as number | null
      if (d != null && d < 0) return 'cell-danger'
      if (d != null && d <= 30) return 'cell-warn'
      return ''
    } },
  { key: 'actions', label: '操作', width: 120, type: 'action', fixed: 'right',
    actions: [
      { label: '编辑', type: 'primary', link: true, perm: 'device:edit', icon: 'Edit',
        onClick: (row) => openEdit(row as unknown as Device) },
      { label: '删除', type: 'danger', link: true, perm: 'device:delete', icon: 'Delete',
        onClick: (row) => onDelete(row as unknown as Device) },
    ] },
])

// 详情
const detailVisible = ref(false)
const detail = ref<Device | null>(null)
const pwdVisible = ref(false)

async function openDetail(row: Record<string, unknown>) {
  const id = row.id as number
  try {
    detail.value = await fetchDevice(id)
    pwdVisible.value = false
    detailVisible.value = true
  } catch { /* toast */ }
}

async function revealPwd() {
  if (!detail.value) return
  if (!pwdVisible.value) {
    const res = await revealPassword(detail.value.id)
    detail.value = { ...detail.value, password: res.password }
    pwdVisible.value = true
  } else {
    pwdVisible.value = false
  }
}

// 表单
const formVisible = ref(false)
const saving = ref(false)
const formRef = ref()
const form = reactive<DeviceForm & { id?: number }>(blankForm())

function blankForm(): DeviceForm & { id?: number } {
  return {
    id: undefined, device_name: '', customer_id: null, device_type: '', brand: '', model: '',
    serial_number: '', ip_address: '', port: 22, username: '', password: '', login_method: 'SSH',
    location: '', interface: [], os_version: '', rule_version: '', is_maintenance: false,
    is_in_use: true, license_expiry: '', license_start: '', remark: '',
  }
}

const formRules = {
  device_name: [{ required: true, message: '请输入设备名称', trigger: 'blur' }],
}

function openCreate() {
  Object.assign(form, blankForm())
  formVisible.value = true
}

async function openEdit(d: Device) {
  Object.assign(form, blankForm(), {
    id: d.id, device_name: d.device_name, customer_id: d.customer_id, device_type: d.device_type,
    brand: d.brand, model: d.model, serial_number: d.serial_number, ip_address: d.ip_address,
    port: d.port, username: d.username, login_method: d.login_method, location: d.location,
    interface: [...d.interface], os_version: d.os_version, rule_version: d.rule_version,
    is_maintenance: d.is_maintenance, is_in_use: d.is_in_use, license_expiry: d.license_expiry,
    license_start: d.license_start, remark: d.remark,
  })
  detailVisible.value = false
  formVisible.value = true
}

async function save() {
  try {
    await formRef.value?.validate()
  } catch {
    return
  }
  saving.value = true
  try {
    const payload = { ...form }
    delete payload.id
    if (form.id) {
      await updateDevice(form.id, payload as DeviceForm)
      ui.toast('设备已更新', 'success')
    } else {
      await createDevice(payload as DeviceForm)
      ui.toast('设备已创建', 'success')
    }
    formVisible.value = false
    tableRef.value?.refresh()
  } catch (e) {
    ui.toast((e as Error).message, 'error')
  } finally {
    saving.value = false
  }
}

async function onDelete(d: Device) {
  try {
    await ElMessageBox.confirm(`确定删除设备「${d.device_name}」吗？`, '删除确认', { type: 'warning' })
  } catch {
    return
  }
  try {
    await deleteDevice(d.id)
    ui.toast('已删除', 'success')
    tableRef.value?.refresh()
  } catch (e) {
    ui.toast((e as Error).message, 'error')
  }
}

function reload() {
  tableRef.value?.refresh()
}

// 初始化字典
import { fetchDeviceDicts } from '@/api/dicts'
fetchDeviceDicts().then((d) => {
  brands.value = d.brands
  deviceTypes.value = d.device_types
  customers.value = d.customers
})
</script>

<style scoped>
.filter-card {
  margin-bottom: 12px;
}
.filter-row {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
  align-items: center;
}
.filter-search {
  width: 220px;
  max-width: 100%;
}
.filter-item {
  width: 140px;
  max-width: 100%;
}
.header-actions {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}
.w-full {
  width: 100%;
}
.flex-gap {
  display: flex;
  gap: 6px;
  width: 100%;
}
.flex-gap .el-input {
  flex: 1;
}
.ml-1 {
  margin-left: 6px;
}
.mr-1 {
  margin-right: 4px;
}
.cell-muted {
  color: var(--itsm-text-muted);
}
.cell-danger {
  color: #f56c6c;
  font-weight: 600;
}
.cell-warn {
  color: #e6a23c;
}
</style>
