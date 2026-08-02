<template>
  <div class="page-container">
    <div class="page-header">
      <h2 class="page-title">机柜管理</h2>
      <div class="header-actions">
        <el-button v-if="user.hasPerm('device:edit')" type="primary" :icon="Plus" @click="openRackForm()">
          新增机柜
        </el-button>
      </div>
    </div>

    <!-- 筛选 -->
    <el-card shadow="never" class="filter-card">
      <div class="filter-row">
        <el-input v-model="query.search" placeholder="搜索机柜名称" clearable class="filter-search"
          @keyup.enter="reload" @clear="reload" />
        <el-select v-model="query.customer_id" placeholder="客户" clearable filterable class="filter-item"
          @change="reload">
          <el-option v-for="c in dicts?.customers || []" :key="c.id" :label="c.name" :value="c.id" />
        </el-select>
        <el-button type="primary" plain :icon="Search" @click="reload">查询</el-button>
      </div>
    </el-card>

    <!-- 列表 -->
    <DataTable
      ref="tableRef"
      :columns="columns"
      :fetch-data="fetchRacks"
      :query="query"
      row-key="id"
      @row-click="openDetail"
    />

    <!-- 机柜详情抽屉（U 位可视化） -->
    <el-drawer v-model="detailVisible" title="" class="rack-drawer" destroy-on-close>
      <div v-if="detail">
        <div class="drawer-title">
          <span class="color-dot" :style="{ background: detail.color }"></span>
          <b>{{ detail.name }}</b>
          <span class="text-muted">{{ detail.customer_name }}</span>
        </div>

        <!-- 统计 -->
        <el-row :gutter="8" class="stat-row">
          <el-col :xs="12" :sm="8"><div class="stat-card"><div class="stat-num">{{ detail.total_u }}U</div><div class="stat-label">总U位</div></div></el-col>
          <el-col :xs="12" :sm="8"><div class="stat-card"><div class="stat-num">{{ detail.used_label }}</div><div class="stat-label">已占用</div></div></el-col>
          <el-col :xs="12" :sm="8"><div class="stat-card"><div class="stat-num">{{ detail.used_pct }}%</div><div class="stat-label">占用率</div></div></el-col>
          <el-col :xs="12" :sm="8"><div class="stat-card"><div class="stat-num">{{ detail.install_count }}</div><div class="stat-label">安装数</div></div></el-col>
          <el-col :xs="12" :sm="8"><div class="stat-card"><div class="stat-num">{{ detail.used_w }}W</div><div class="stat-label">当前功耗</div></div></el-col>
          <el-col :xs="12" :sm="8"><div class="stat-card"><div class="stat-num">{{ detail.pdu_total_w }}W</div><div class="stat-label">PDU额定</div></div></el-col>
        </el-row>

        <el-divider content-position="left">U 位布局（点击空位上架 / 点击设备调整）</el-divider>
        <div class="rack-frame">
          <div class="rack-frame-header" :style="{ background: detail.color }">{{ detail.name }}</div>
          <div class="rack-u">
            <div v-for="row in uRows" :key="row.u" class="u-row"
              :class="{ empty: !row.install, installed: !!row.install }"
              :style="row.install ? { background: detail.color } : {}"
              :title="row.install ? `${row.install.name} (${row.install.start_u}-${row.install.start_u + row.install.occupy_u - 1}U)` : ''"
              @click="row.install ? openAdjust(row.install) : openInstall(row.u)">
              <span class="u-label">{{ row.u }}U</span>
              <span class="u-content">
                <template v-if="row.install && row.isBlockTop">
                  <b>{{ row.install.name }}</b>
                  <span class="u-sub">{{ row.install.brand }} {{ row.install.model }} {{ row.install.ip }}</span>
                </template>
                <span v-else-if="!row.install">空</span>
              </span>
            </div>
          </div>
        </div>

        <!-- 已上架设备列表 -->
        <el-divider content-position="left">已上架设备</el-divider>
        <el-empty v-if="!detail.installs.length" description="暂无上架设备" :image-size="50" />
        <div v-for="inst in detail.installs" :key="inst.id" class="install-item">
          <div class="install-info">
            <el-tag size="small" :type="inst.kind === '托管' ? 'primary' : 'warning'" class="install-kind">
              {{ inst.kind }}
            </el-tag>
            <b>{{ inst.name }}</b>
            <span class="text-muted">{{ inst.start_u }}-{{ inst.start_u + inst.occupy_u - 1 }}U · {{ inst.rated_w }}W</span>
            <span v-if="inst.ip" class="text-muted">{{ inst.ip }}</span>
          </div>
          <div class="install-actions">
            <el-button v-if="user.hasPerm('device:edit')" size="small" type="primary" link @click="openAdjust(inst)">
              调整
            </el-button>
            <el-button v-if="user.hasPerm('device:delete')" size="small" type="danger" link @click="onUninstall(inst)">
              下架
            </el-button>
          </div>
        </div>
      </div>
    </el-drawer>

    <!-- 新增/编辑机柜 -->
    <el-dialog v-model="rackFormVisible" :title="rackForm.id ? '编辑机柜' : '新增机柜'" width="520px" top="8vh"
      destroy-on-close>
      <el-form ref="rackFormRef" :model="rackForm" :rules="rackFormRules" label-width="100px">
        <el-form-item label="名称" prop="name">
          <el-input v-model="rackForm.name" placeholder="如：A-01" />
        </el-form-item>
        <el-form-item label="所属客户" prop="customer_id">
          <el-select v-model="rackForm.customer_id" filterable class="w-full">
            <el-option v-for="c in dicts?.customers || []" :key="c.id" :label="c.name" :value="c.id" />
          </el-select>
        </el-form-item>
        <el-row :gutter="12">
          <el-col :xs="24" :sm="12">
            <el-form-item label="总U数" prop="total_u">
              <el-input-number v-model="rackForm.total_u" :min="1" :max="120" class="w-full" />
            </el-form-item>
          </el-col>
          <el-col :xs="24" :sm="12">
            <el-form-item label="PDU功率">
              <el-input-number v-model="rackForm.pdu_total_w" :min="0" :step="500" class="w-full" />
            </el-form-item>
          </el-col>
        </el-row>
        <el-form-item label="显示颜色">
          <el-color-picker v-model="rackForm.color" />
        </el-form-item>
        <el-form-item label="备注">
          <el-input v-model="rackForm.remark" type="textarea" :rows="2" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="rackFormVisible = false">取消</el-button>
        <el-button type="primary" :loading="rackSaving" @click="saveRack">保存</el-button>
      </template>
    </el-dialog>

    <!-- 上架/调整 -->
    <el-dialog v-model="installVisible" :title="installForm.id ? '调整安装位置' : '设备上架'" width="560px" top="5vh"
      destroy-on-close>
      <el-form ref="installFormRef" :model="installForm" :rules="installFormRules" label-width="90px">
        <template v-if="!installForm.id">
          <el-form-item label="上架方式">
            <el-radio-group v-model="installMode">
              <el-radio value="device">选择设备</el-radio>
              <el-radio value="manual">手动录入</el-radio>
            </el-radio-group>
          </el-form-item>
          <el-form-item v-if="installMode === 'device'" label="设备" prop="device_id">
            <el-select v-model="installForm.device_id" filterable class="w-full">
              <el-option v-for="d in devices" :key="d.id" :value="d.id" :disabled="d.installed"
                :label="`${d.name}${d.installed ? '（已上架）' : ''} · ${d.ip || d.brand + ' ' + d.model}`" />
            </el-select>
          </el-form-item>
          <template v-else>
            <el-form-item label="设备名" prop="manual_name">
              <el-input v-model="installForm.manual_name" placeholder="手动设备名称（必填）" />
            </el-form-item>
            <el-row :gutter="12">
              <el-col :xs="24" :sm="12">
                <el-form-item label="品牌"><el-input v-model="installForm.manual_brand" /></el-form-item>
              </el-col>
              <el-col :xs="24" :sm="12">
                <el-form-item label="型号"><el-input v-model="installForm.manual_model" /></el-form-item>
              </el-col>
            </el-row>
            <el-form-item label="IP"><el-input v-model="installForm.manual_ip" /></el-form-item>
          </template>
        </template>
        <template v-else>
          <el-form-item label="设备">
            <span v-if="editingInstall">{{ editingInstall.name }}（{{ editingInstall.kind }}）</span>
          </el-form-item>
        </template>
        <el-row :gutter="12">
          <el-col :xs="12" :sm="8">
            <el-form-item label="起始U" prop="start_u">
              <el-input-number v-model="installForm.start_u" :min="1" :max="detail?.total_u || 42" class="w-full" />
            </el-form-item>
          </el-col>
          <el-col :xs="12" :sm="8">
            <el-form-item label="占用U" prop="occupy_u">
              <el-input-number v-model="installForm.occupy_u" :min="1" :max="10" class="w-full" />
            </el-form-item>
          </el-col>
          <el-col :xs="24" :sm="8">
            <el-form-item label="功耗(W)">
              <el-input-number v-model="installForm.rated_w" :min="0" :step="50" class="w-full" />
            </el-form-item>
          </el-col>
        </el-row>
        <el-form-item label="备注">
          <el-input v-model="installForm.remark" type="textarea" :rows="2" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="installVisible = false">取消</el-button>
        <el-button type="primary" :loading="installSaving" @click="saveInstall">保存</el-button>
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
  fetchRacks, fetchRack, createRack, updateRack, deleteRack,
  fetchRackDevices, createInstall, updateInstall, deleteInstall, fetchRackDicts,
  USAGE_LEVEL_TAG,
  type RackItem, type RackDetail, type RackInstall, type RackDevice, type RackDicts,
} from '@/api/rack'

const user = useUserStore()
const ui = useUiStore()
const dicts = ref<RackDicts | null>(null)

const query = reactive<Record<string, unknown>>({ search: '', customer_id: undefined })
const tableRef = ref()

const columns = computed<DataColumn[]>(() => [
  { key: 'name', label: '名称', minWidth: 140, asTitle: true, align: 'left' },
  { key: 'customer_name', label: '客户', minWidth: 110 },
  { key: 'used_label', label: 'U位占用', width: 90, align: 'center' },
  { key: 'usage_level', label: '占用率', width: 90, type: 'tag', asTag: true,
    tagMap: USAGE_LEVEL_TAG },
  { key: 'used_w', label: '功率(W)', width: 90, align: 'right' },
  { key: 'install_count', label: '安装数', width: 80, align: 'center' },
  { key: 'actions', label: '操作', width: 130, type: 'action', fixed: 'right',
    actions: [
      { label: '详情', type: 'primary', link: true, perm: 'device:view', icon: 'View',
        onClick: (row) => openDetail(row) },
      { label: '编辑', type: 'warning', link: true, perm: 'device:edit', icon: 'Edit',
        onClick: (row) => openRackForm(row) },
      { label: '删除', type: 'danger', link: true, perm: 'device:delete', icon: 'Delete',
        onClick: (row) => onDeleteRack(row) },
    ] },
])

// ==================== 详情抽屉 + U 位可视化 ====================
const detailVisible = ref(false)
const detail = ref<RackDetail | null>(null)

interface URow { u: number; install: RackInstall | null; isBlockTop: boolean }

const uRows = computed<URow[]>(() => {
  const d = detail.value
  if (!d) return []
  const map = new Map<number, RackInstall>()
  for (const inst of d.installs) {
    for (let u = inst.start_u; u < inst.start_u + inst.occupy_u; u++) map.set(u, inst)
  }
  const rows: URow[] = []
  for (let u = d.total_u; u >= 1; u--) {
    const inst = map.get(u) || null
    rows.push({ u, install: inst, isBlockTop: !!inst && u === inst.start_u + inst.occupy_u - 1 })
  }
  return rows
})

async function openDetail(row: Record<string, unknown>) {
  try {
    detail.value = await fetchRack(row.id as number)
    detailVisible.value = true
  } catch { /* toast */ }
}

function lowestFreeU(): number {
  const d = detail.value
  if (!d) return 1
  const busy = new Set<number>()
  for (const inst of d.installs) {
    for (let u = inst.start_u; u < inst.start_u + inst.occupy_u; u++) busy.add(u)
  }
  for (let u = 1; u <= d.total_u; u++) if (!busy.has(u)) return u
  return d.total_u
}

// ==================== 上架 / 调整 ====================
const installVisible = ref(false)
const installSaving = ref(false)
const installMode = ref<'device' | 'manual'>('device')
const devices = ref<RackDevice[]>([])
const editingInstall = ref<RackInstall | null>(null)
const installFormRef = ref()
const installForm = reactive<Record<string, unknown>>({
  id: null, rack_id: null, device_id: null,
  manual_name: '', manual_brand: '', manual_model: '', manual_ip: '',
  start_u: 1, occupy_u: 1, rated_w: 0, remark: '',
})
const installFormRules = {
  device_id: [{ required: true, message: '请选择设备', trigger: 'change' }],
  manual_name: [{ required: true, message: '请输入设备名称', trigger: 'blur' }],
  start_u: [{ required: true, message: '请输入起始U位', trigger: 'change' }],
  occupy_u: [{ required: true, message: '请输入占用U数', trigger: 'change' }],
}

async function openInstall(startU: number) {
  if (!detail.value) return
  Object.assign(installForm, {
    id: null, rack_id: detail.value.id, device_id: null,
    manual_name: '', manual_brand: '', manual_model: '', manual_ip: '',
    start_u: startU, occupy_u: 1, rated_w: 0, remark: '',
  })
  editingInstall.value = null
  installMode.value = 'device'
  devices.value = []
  try {
    devices.value = (await fetchRackDevices({ rack_id: detail.value.id })).items
  } catch { /* toast */ }
  installVisible.value = true
}

function openAdjust(inst: RackInstall) {
  Object.assign(installForm, {
    id: inst.id, rack_id: inst.rack_id, device_id: inst.device_id,
    manual_name: inst.name, manual_brand: inst.brand, manual_model: inst.model,
    manual_ip: inst.ip, start_u: inst.start_u, occupy_u: inst.occupy_u,
    rated_w: inst.rated_w, remark: inst.remark,
  })
  editingInstall.value = inst
  installVisible.value = true
}

async function saveInstall() {
  try { await installFormRef.value?.validate() } catch { return }
  installSaving.value = true
  try {
    const payload: Record<string, unknown> = {
      rack_id: installForm.rack_id,
      start_u: installForm.start_u,
      occupy_u: installForm.occupy_u,
      rated_w: installForm.rated_w,
      remark: installForm.remark,
    }
    if (installForm.id) {
      await updateInstall(installForm.id as number, payload)
    } else {
      if (installMode.value === 'device') {
        payload.device_id = installForm.device_id
      } else {
        payload.manual_name = installForm.manual_name
        payload.manual_brand = installForm.manual_brand
        payload.manual_model = installForm.manual_model
        payload.manual_ip = installForm.manual_ip
      }
      await createInstall(payload)
    }
    ui.toast('保存成功', 'success')
    installVisible.value = false
    if (detail.value) detail.value = await fetchRack(detail.value.id)
    tableRef.value?.refresh()
  } catch (e) {
    ui.toast((e as Error).message, 'error')
  } finally {
    installSaving.value = false
  }
}

async function onUninstall(inst: RackInstall) {
  try {
    await ElMessageBox.confirm(`确定将「${inst.name}」下架吗？`, '下架确认', { type: 'warning' })
  } catch { return }
  try {
    await deleteInstall(inst.id)
    ui.toast('已下架', 'success')
    if (detail.value) detail.value = await fetchRack(detail.value.id)
    tableRef.value?.refresh()
  } catch (e) {
    ui.toast((e as Error).message, 'error')
  }
}

// ==================== 机柜新增/编辑 ====================
const rackFormVisible = ref(false)
const rackSaving = ref(false)
const rackFormRef = ref()
const rackForm = reactive<Record<string, unknown>>({
  id: null, name: '', customer_id: null, total_u: 42, pdu_total_w: 0, color: '#0d6efd', remark: '',
})
const rackFormRules = {
  name: [{ required: true, message: '请输入机柜名称', trigger: 'blur' }],
  customer_id: [{ required: true, message: '请选择所属客户', trigger: 'change' }],
}

function openRackForm(row?: Record<string, unknown>) {
  Object.assign(rackForm, {
    id: row?.id ?? null,
    name: row?.name ?? '',
    customer_id: row?.customer_id ?? null,
    total_u: row?.total_u ?? 42,
    pdu_total_w: row?.pdu_total_w ?? 0,
    color: row?.color ?? '#0d6efd',
    remark: row?.remark ?? '',
  })
  rackFormVisible.value = true
}

async function saveRack() {
  try { await rackFormRef.value?.validate() } catch { return }
  rackSaving.value = true
  try {
    const payload = {
      name: rackForm.name as string,
      customer_id: rackForm.customer_id as number,
      total_u: rackForm.total_u as number,
      pdu_total_w: rackForm.pdu_total_w as number,
      color: rackForm.color as string,
      remark: rackForm.remark as string,
    }
    if (rackForm.id) {
      await updateRack(rackForm.id as number, payload)
    } else {
      await createRack(payload)
    }
    ui.toast('保存成功', 'success')
    rackFormVisible.value = false
    tableRef.value?.refresh()
  } catch (e) {
    ui.toast((e as Error).message, 'error')
  } finally {
    rackSaving.value = false
  }
}

async function onDeleteRack(row: Record<string, unknown>) {
  try {
    await ElMessageBox.confirm(`确定删除机柜「${row.name}」吗？机柜内已上架设备将一并下架。`, '删除确认', {
      type: 'warning',
    })
  } catch { return }
  try {
    await deleteRack(row.id as number)
    ui.toast('已删除', 'success')
    if (detail.value?.id === row.id) detailVisible.value = false
    tableRef.value?.refresh()
  } catch (e) {
    ui.toast((e as Error).message, 'error')
  }
}

function reload() { tableRef.value?.refresh() }

onMounted(() => {
  fetchRackDicts().then((d) => (dicts.value = d))
})
</script>

<style scoped>
.filter-card { margin-bottom: 12px; }
.filter-row { display: flex; gap: 8px; flex-wrap: wrap; align-items: center; }
.filter-search { width: 200px; max-width: 100%; }
.filter-item { width: 160px; max-width: 100%; }
.header-actions { display: flex; gap: 8px; flex-wrap: wrap; }
.w-full { width: 100%; }
.text-muted { color: var(--itsm-text-muted); font-size: 12px; margin-left: 8px; }
.drawer-title { display: flex; align-items: center; gap: 8px; margin-bottom: 12px; font-size: 16px; }
.color-dot { width: 14px; height: 14px; border-radius: 3px; display: inline-block; }
.stat-row { margin-bottom: 4px; }
.stat-card { background: var(--itsm-card-bg); border: 1px solid var(--itsm-border);
  border-radius: 8px; padding: 8px 10px; margin-bottom: 8px; }
.stat-num { font-size: 15px; font-weight: 600; }
.stat-label { color: var(--itsm-text-muted); font-size: 12px; }

/* U 位可视化 */
.rack-frame { max-width: 340px; border: 1px solid var(--itsm-border); border-radius: 8px; padding: 8px; }
.rack-frame-header { color: #fff; text-align: center; font-size: 13px; padding: 4px 0;
  border-radius: 4px 4px 0 0; }
.rack-u { display: flex; flex-direction: column; gap: 1px; padding: 4px 0; }
.u-row { height: 20px; font-size: 12px; padding: 0 4px; display: flex; align-items: center;
  border-left: 3px solid var(--itsm-border); cursor: default; border-radius: 2px; }
.u-row.empty { background: var(--el-fill-color-light); color: var(--itsm-text-muted); cursor: pointer; }
.u-row.empty:hover { border-left-color: var(--el-color-primary); }
.u-row.installed { color: #fff; cursor: pointer; }
.u-row.installed:hover { filter: brightness(0.9); }
.u-row .u-label { width: 34px; flex-shrink: 0; opacity: 0.75; font-family: var(--font-mono, monospace); }
.u-row .u-content { flex-grow: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.u-sub { margin-left: 6px; opacity: 0.85; }

/* 上架设备列表 */
.install-item { display: flex; justify-content: space-between; align-items: center; gap: 8px;
  padding: 8px 10px; border: 1px solid var(--itsm-border); border-radius: 8px; margin-bottom: 8px; }
.install-info { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; min-width: 0; }
.install-kind { flex-shrink: 0; }
.install-actions { display: flex; flex-shrink: 0; }
</style>
