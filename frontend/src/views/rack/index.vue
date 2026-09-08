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

    <!-- 左侧：客户 → 机房 → 机柜 树 + 右侧：内联详情 -->
    <el-row :gutter="12" class="rack-body">
      <el-col :xs="24" :md="6">
        <el-card shadow="never" class="tree-card">
          <div class="tree-header">
            <span class="tree-title">客户 / 机房 / 机柜</span>
            <el-button size="small" text :icon="Refresh" @click="loadTree" />
          </div>
          <el-tree
            :data="treeData"
            node-key="id"
            :props="{ label: 'label', children: 'children' }"
            :expand-on-click-node="true"
            :highlight-current="true"
            :current-node-key="currentNodeKey"
            :default-expanded-keys="expandedKeys"
            class="rack-tree"
            @node-click="onTreeClick"
          >
            <template #default="{ data }">
              <span class="tree-node">
                <span v-if="data.color" class="tree-color-dot" :style="{ background: data.color }"></span>
                <span v-else-if="data.type === 'rack'" class="tree-color-dot rack-dot"></span>
                <span class="tree-label">{{ data.label }}</span>
                <span v-if="data.type === 'rack'" class="tree-count">{{ data.install_count ?? '' }}</span>
              </span>
            </template>
          </el-tree>
          <div v-if="!treeData.length" class="tree-empty">暂无机柜，点上方「新增机柜」</div>
        </el-card>
      </el-col>

      <el-col :xs="24" :md="18">
        <el-card shadow="never" class="detail-card">
          <!-- 未选中 -->
          <div v-if="!detail" class="detail-empty">
            <el-icon :size="52" class="empty-icon"><Collection /></el-icon>
            <p class="text-muted">请从左侧选择机柜查看详情</p>
          </div>

          <div v-else>
            <!-- 标题 + 操作 -->
            <div class="rack-title-row">
              <span class="color-dot" :style="{ background: detail.color }"></span>
              <b class="rack-name">{{ detail.name }}</b>
              <span class="text-muted">{{ detail.customer_name }}</span>
              <span class="text-muted">{{ detail.location || '未填写机房' }}</span>
              <div class="rack-actions">
                <el-button v-if="user.hasPerm('device:edit')" size="small" type="success"
                  :icon="Plus" @click="openInstall()">设备上架</el-button>
                <el-button v-if="user.hasPerm('device:edit')" size="small" type="primary"
                  plain :icon="Edit" @click="openRackForm(detail)">编辑</el-button>
                <el-button v-if="user.hasPerm('device:delete')" size="small" type="danger"
                  plain :icon="Delete" @click="onDeleteRack">删除</el-button>
              </div>
            </div>

            <!-- 统计 -->
            <div class="rack-summary">
              <div class="stat-card"><span class="stat-num">{{ detail.total_u }}U</span><span class="stat-label">总U位</span></div>
              <div class="stat-card"><span class="stat-num">{{ detail.used_label }}</span><span class="stat-label">已占用</span></div>
              <div class="stat-card"><span class="stat-num">{{ detail.used_pct }}%</span><span class="stat-label">占用率</span></div>
              <div class="stat-card"><span class="stat-num">{{ detail.install_count }}</span><span class="stat-label">安装数</span></div>
              <div class="stat-card"><span class="stat-num">{{ detail.used_w }} W</span><span class="stat-label">已知总额定功率</span></div>
              <div class="stat-card"><span class="stat-num">{{ detail.power_completeness }}%</span><span class="stat-label">功率完整率（缺 {{ detail.unknown_power_count }}）</span></div>
              <div class="stat-card"><span class="stat-num">{{ detail.pdu_total_w }} W</span><span class="stat-label">PDU 额定容量</span></div>
              <div class="stat-card"><span class="stat-num">{{ detail.pdu_remaining_w == null ? '-' : `${detail.pdu_remaining_w} W` }}</span><span class="stat-label">PDU 剩余容量</span></div>
              <div class="stat-card"><span class="stat-num">{{ detail.pdu_load_pct == null ? '-' : `${detail.pdu_load_pct}%` }}</span><span class="stat-label">PDU 已知负载率</span></div>
              <div class="stat-card"><span class="stat-num">{{ detail.heat_btu_h }} BTU/h</span><span class="stat-label">已知设备热负荷</span></div>
            </div>
            <div class="capacity-status">
              <span v-if="detail.unknown_power_count" class="capacity-warning">
                仍有 {{ detail.unknown_power_count }} 台设备未核实额定功率
              </span>
              <span v-if="detail.pdu_load_pct != null && detail.pdu_load_pct > 100" class="capacity-danger">
                已知额定功率已超过 PDU 额定容量
              </span>
              <el-tooltip placement="top" :show-after="250">
                <template #content>
                  热负荷按已知设备额定功率 × 3.412 换算，不含人员、照明、环境和冗余。<br>
                  UPS 建议容量需结合功率因数、目标负载率和冗余系数计算。
                </template>
                <span class="capacity-help"><el-icon><InfoFilled /></el-icon>容量口径</span>
              </el-tooltip>
            </div>

            <!-- U 位图 + 设备表（左右布局） -->
            <div class="rack-visual">
              <div class="rack-frame">
                <div class="rack-frame-header" :style="{ background: detail.color }">{{ detail.name }}</div>
                <div class="rack-side-switch">
                  <el-radio-group v-model="rackViewSide" size="small">
                    <el-radio-button value="正面">正面</el-radio-button>
                    <el-radio-button value="背面">背面</el-radio-button>
                  </el-radio-group>
                </div>
                <div class="rack-u">
                  <div v-for="row in uRows" :key="row.u" class="u-row"
                    :class="{ empty: !row.install, installed: !!row.install }"
                    :style="row.install ? { background: detail.color } : {}"
                    :title="row.install ? `${row.install.name} (${row.install.start_u}-${row.install.start_u + row.install.occupy_u - 1}U)` : ''"
                    @click="row.install ? openAdjust(row.install) : openInstall(row.u)">
                    <span class="u-label">{{ row.u }}U</span>
                    <span class="u-content">
                      <template v-if="row.install && row.isBlockTop">
                        <b :style="{ color: inactiveDeviceColor(row.install.is_in_use) }"
                          :title="row.install.is_in_use === false ? '已停用' : undefined">{{ row.install.name }}</b>
                        <span class="u-sub">{{ row.install.brand }} {{ row.install.model }} {{ row.install.ip }}</span>
                      </template>
                      <span v-else-if="!row.install">空</span>
                    </span>
                  </div>
                </div>
                <div class="rack-frame-hint text-muted">点击空位上架 / 点击设备调整</div>
              </div>

              <div class="install-table-wrap">
                <DataTable
                  :columns="installColumns"
                  :fetch-data="fetchInstallPage"
                  :query="{ rack_id: detail.id, revision: installRevision }"
                  row-key="id"
                  empty-text="暂无上架设备"
                  :column-settings="{ storageKey: 'cols_rack_installs_v2' }"
                >
                  <template #cell-name="{ row }">
                    <span :style="{ color: inactiveDeviceColor(row.is_in_use) }"
                      :title="row.is_in_use === false ? '已停用' : undefined">{{ row.name }}</span>
                  </template>
                </DataTable>
              </div>
            </div>
          </div>
        </el-card>
      </el-col>
    </el-row>

    <!-- 新增/编辑机柜 -->
    <el-dialog v-model="rackFormVisible" :title="rackForm.id ? '编辑机柜' : '新增机柜'" width="520px" top="8vh"
      destroy-on-close>
      <el-form ref="rackFormRef" :model="rackForm" :rules="rackFormRules" label-width="100px">
        <el-form-item :label="rackLabel('name', '机柜名称', 'form')" prop="name">
          <el-input v-model="rackForm.name" placeholder="如：A-01" />
        </el-form-item>
        <el-form-item :label="rackLabel('customer_name', '所属客户', 'form')" prop="customer_id">
          <el-select v-model="rackForm.customer_id" filterable class="w-full">
            <el-option v-for="c in dicts?.customers || []" :key="c.id" :label="c.name" :value="c.id" />
          </el-select>
        </el-form-item>
        <el-form-item :label="rackLabel('location', '机房位置', 'form')">
          <el-input v-model="rackForm.location" placeholder="如：2F 机房 B 区" />
        </el-form-item>
        <el-row :gutter="12">
          <el-col :xs="24" :sm="12">
            <el-form-item :label="rackLabel('total_u', '总U数', 'form')" prop="total_u">
              <el-input-number v-model="rackForm.total_u" :min="1" :max="120" class="w-full" />
            </el-form-item>
          </el-col>
          <el-col :xs="24" :sm="12">
            <el-form-item :label="rackLabel('pdu_total_w', 'PDU功率(W)', 'form')">
              <el-input-number v-model="rackForm.pdu_total_w" :min="0" :step="500" class="w-full" />
            </el-form-item>
          </el-col>
        </el-row>
        <el-form-item :label="rackLabel('color', '显示颜色', 'form')">
          <el-color-picker v-model="rackForm.color" />
        </el-form-item>
        <el-form-item :label="rackLabel('remark', '备注', 'form')">
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
          <el-form-item v-if="installMode === 'device'" :label="installLabel('name', '设备名称', 'form')" prop="device_id">
            <el-select v-model="installForm.device_id" filterable class="w-full">
              <el-option v-for="d in devices" :key="d.id" :value="d.id" :disabled="d.installed"
                :label="`${d.name}${d.installed ? '（已上架）' : ''} · ${d.ip || d.brand + ' ' + d.model}`" />
            </el-select>
          </el-form-item>
          <template v-else>
            <el-form-item :label="installLabel('name', '设备名称', 'form')" prop="manual_name">
              <el-input v-model="installForm.manual_name" placeholder="手动设备名称（必填）" />
            </el-form-item>
            <el-row :gutter="12">
              <el-col :xs="24" :sm="12">
                <el-form-item :label="installLabel('brand', '品牌', 'form')"><el-input v-model="installForm.manual_brand" /></el-form-item>
              </el-col>
              <el-col :xs="24" :sm="12">
                <el-form-item :label="installLabel('model', '型号', 'form')"><el-input v-model="installForm.manual_model" /></el-form-item>
              </el-col>
            </el-row>
            <el-form-item :label="installLabel('ip', 'IP', 'form')"><el-input v-model="installForm.manual_ip" /></el-form-item>
          </template>
        </template>
        <template v-else>
          <el-form-item label="设备">
            <span v-if="editingInstall">{{ editingInstall.name }}（{{ editingInstall.kind }}）</span>
          </el-form-item>
        </template>
        <el-form-item :label="installLabel('install_side', '安装位置', 'form')" prop="install_side">
          <el-radio-group v-model="installForm.install_side">
            <el-radio-button value="正面">正面</el-radio-button>
            <el-radio-button value="背面">背面</el-radio-button>
          </el-radio-group>
        </el-form-item>
        <el-row :gutter="12">
          <el-col :xs="12" :sm="8">
            <el-form-item :label="installLabel('start_u', '起始U位', 'form')" prop="start_u">
              <el-input-number v-model="installForm.start_u" :min="1" :max="detail?.total_u || 42" class="w-full" />
            </el-form-item>
          </el-col>
          <el-col :xs="12" :sm="8">
            <el-form-item :label="installLabel('occupy_u', '占用U数', 'form')" prop="occupy_u">
              <el-input-number v-model="installForm.occupy_u" :min="1" :max="10" class="w-full" />
            </el-form-item>
          </el-col>
          <el-col :xs="24" :sm="8">
            <el-form-item :label="deviceLabel('rated_power_w', '额定功率', 'form')">
              <el-input-number v-if="isManualPowerEditable" v-model="installForm.rated_w"
                :min="0" :step="50" class="w-full" />
              <span v-else>{{ linkedRatedPower == null ? '未核实（请到设备编辑中填写）' : `${linkedRatedPower} W` }}</span>
            </el-form-item>
          </el-col>
        </el-row>
        <el-form-item :label="installLabel('remark', '备注', 'form')">
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
import { ElMessageBox } from 'element-plus/es/components/message-box/index'
import { ref, reactive, computed, onMounted } from 'vue'
import { inactiveDeviceColor } from '@/utils/deviceName'
import { Plus, Refresh, Edit, Delete, Collection, InfoFilled } from '@element-plus/icons-vue'
import { useUserStore } from '@/stores/user'
import { useUiStore } from '@/stores/ui'
import {
  fetchRack, createRack, updateRack, deleteRack,
  fetchRackDevices, createInstall, updateInstall, deleteInstall, fetchRackDicts,
  fetchRackTree,
  type RackDetail, type RackInstall, type RackDevice, type RackDicts,
} from '@/api/rack'
import { entityFieldLabel, fetchEntityMetas, type EntityMeta } from '@/api/meta'
import DataTable, { type DataColumn } from '@/components/DataTable.vue'

const user = useUserStore()
const ui = useUiStore()
const dicts = ref<RackDicts | null>(null)
const metas = ref<Record<string, EntityMeta>>({})

function rackLabel(key: string, fallback: string, profile = 'detail') {
  return entityFieldLabel(metas.value.rack, key, fallback, profile)
}

function installLabel(key: string, fallback: string, profile = 'list') {
  return entityFieldLabel(metas.value.rack_install, key, fallback, profile)
}

function deviceLabel(key: string, fallback: string, profile = 'list') {
  return entityFieldLabel(metas.value.device, key, fallback, profile)
}

const installRevision = ref(0)
const installColumns = computed<DataColumn[]>(() => [
  { key: 'start_u', label: deviceLabel('rack_slot', '起始U位'), width: 105, align: 'center',
    render: (row) => Number(row.occupy_u) <= 1 ? `${row.start_u}U`
      : `${row.start_u}U-${Number(row.start_u) + Number(row.occupy_u) - 1}U` },
  { key: 'name', label: deviceLabel('device_name', '名称'), minWidth: 140, asTitle: true },
  { key: 'brand', label: deviceLabel('brand', '品牌'), minWidth: 100 },
  { key: 'model', label: deviceLabel('model', '型号'), minWidth: 110 },
  { key: 'ip', label: deviceLabel('ip_address', 'IP'), minWidth: 110 },
  { key: 'rated_power_w', label: deviceLabel('rated_power_w', '额定功率'), width: 105,
    align: 'right', render: (row) => row.rated_power_w == null ? '' : `${row.rated_power_w} W` },
  { key: 'actions', label: '操作', width: 110, type: 'action', fixed: 'right', actions: [
    { label: '调整', type: 'primary', link: true, perm: 'device:edit',
      onClick: (row) => openAdjust(row as unknown as RackInstall) },
    { label: '下架', type: 'danger', link: true, perm: 'device:delete',
      onClick: (row) => onUninstall(row as unknown as RackInstall) },
  ] },
])

async function fetchInstallPage(params: Record<string, unknown>) {
  const rows = detail.value?.installs || []
  const page = Number(params.page) || 1
  const page_size = Number(params.page_size) || 20
  const start = (page - 1) * page_size
  return { items: rows.slice(start, start + page_size), total: rows.length, page, page_size }
}

// ==================== 客户 → 机房 → 机柜 树 ====================
import { buildRackTree, type TreeNode } from './tree'

const treeData = ref<TreeNode[]>([])
const expandedKeys = ref<string[]>([])
const currentNodeKey = ref<string>('')

async function loadTree() {
  try {
    const cities = await fetchRackTree()
    const nodes = buildRackTree(cities)
    treeData.value = nodes
    expandedKeys.value = nodes.map((n) => n.id)
  } catch { /* toast */ }
}

function onTreeClick(node: TreeNode) {
  if (node.type === 'rack') {
    selectRack(Number(node.id.split('-')[1]))
  }
}

// ==================== 内联详情 + U 位可视化 ====================
const detail = ref<RackDetail | null>(null)
const rackViewSide = ref<'正面' | '背面'>('正面')

async function selectRack(id: number) {
  try {
    detail.value = await fetchRack(id)
    installRevision.value += 1
    currentNodeKey.value = `rack-${id}`
  } catch (e) {
    ui.toast((e as Error).message, 'error')
  }
}

interface URow { u: number; install: RackInstall | null; isBlockTop: boolean }

const uRows = computed<URow[]>(() => {
  const d = detail.value
  if (!d) return []
  const map = new Map<number, RackInstall>()
  for (const inst of d.installs.filter((item) => (item.install_side || '正面') === rackViewSide.value)) {
    for (let u = inst.start_u; u < inst.start_u + inst.occupy_u; u++) map.set(u, inst)
  }
  const rows: URow[] = []
  for (let u = d.total_u; u >= 1; u--) {
    const inst = map.get(u) || null
    rows.push({ u, install: inst, isBlockTop: !!inst && u === inst.start_u + inst.occupy_u - 1 })
  }
  return rows
})

// ==================== 上架 / 调整 ====================
const installVisible = ref(false)
const installSaving = ref(false)
const installMode = ref<'device' | 'manual'>('device')
const devices = ref<RackDevice[]>([])
const editingInstall = ref<RackInstall | null>(null)
const linkedRatedPower = computed(() => {
  if (editingInstall.value?.device_id) return editingInstall.value.rated_power_w
  const selected = devices.value.find((item) => item.id === Number(installForm.device_id))
  return selected?.rated_power_w ?? null
})
const isManualPowerEditable = computed(() =>
  editingInstall.value ? !editingInstall.value.device_id : installMode.value === 'manual')
const installFormRef = ref()
const installForm = reactive<Record<string, unknown>>({
  id: null, rack_id: null, device_id: null,
  manual_name: '', manual_brand: '', manual_model: '', manual_ip: '',
  start_u: 1, occupy_u: 1, install_side: '正面', rated_w: 0, remark: '',
})
const installFormRules = {
  device_id: [{ required: true, message: '请选择设备', trigger: 'change' }],
  manual_name: [{ required: true, message: '请输入设备名称', trigger: 'blur' }],
  start_u: [{ required: true, message: '请输入起始U位', trigger: 'change' }],
  occupy_u: [{ required: true, message: '请输入占用U数', trigger: 'change' }],
  install_side: [{ required: true, message: '请选择安装位置', trigger: 'change' }],
}

async function openInstall(startU = 1) {
  if (!detail.value) return
  Object.assign(installForm, {
    id: null, rack_id: detail.value.id, device_id: null,
    manual_name: '', manual_brand: '', manual_model: '', manual_ip: '',
    start_u: startU, occupy_u: 1, install_side: rackViewSide.value, rated_w: 0, remark: '',
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
    install_side: inst.install_side || '正面', rated_w: inst.rated_w, remark: inst.remark,
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
      install_side: installForm.install_side,
      remark: installForm.remark,
    }
    if (isManualPowerEditable.value) payload.rated_w = installForm.rated_w
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
    if (detail.value) {
      detail.value = await fetchRack(detail.value.id)
      installRevision.value += 1
    }
    loadTree()
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
    if (detail.value) {
      detail.value = await fetchRack(detail.value.id)
      installRevision.value += 1
    }
    loadTree()
  } catch (e) {
    ui.toast((e as Error).message, 'error')
  }
}

// ==================== 机柜新增/编辑 ====================
const rackFormVisible = ref(false)
const rackSaving = ref(false)
const rackFormRef = ref()
const rackForm = reactive<Record<string, unknown>>({
  id: null, name: '', customer_id: null, location: '', total_u: 42, pdu_total_w: 0,
  color: '#0d6efd', remark: '',
})
const rackFormRules = {
  name: [{ required: true, message: '请输入机柜名称', trigger: 'blur' }],
  customer_id: [{ required: true, message: '请选择所属客户', trigger: 'change' }],
}

function openRackForm(row?: RackDetail) {
  Object.assign(rackForm, {
    id: row?.id ?? null,
    name: row?.name ?? '',
    customer_id: row?.customer_id ?? null,
    location: row?.location ?? '',
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
      location: rackForm.location as string,
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
    if (detail.value && detail.value.id === rackForm.id) {
      detail.value = await fetchRack(detail.value.id)
      installRevision.value += 1
    }
    loadTree()
  } catch (e) {
    ui.toast((e as Error).message, 'error')
  } finally {
    rackSaving.value = false
  }
}

async function onDeleteRack() {
  if (!detail.value) return
  try {
    await ElMessageBox.confirm(
      `确定删除机柜「${detail.value.name}」吗？机柜内已上架设备将一并下架。`,
      '删除确认', { type: 'warning' })
  } catch { return }
  try {
    await deleteRack(detail.value.id)
    ui.toast('已删除', 'success')
    detail.value = null
    currentNodeKey.value = ''
    loadTree()
  } catch (e) {
    ui.toast((e as Error).message, 'error')
  }
}

onMounted(() => {
  fetchRackDicts().then((d) => (dicts.value = d))
  loadTree()
  fetchEntityMetas(['rack', 'rack_install', 'device'])
    .then((result) => { metas.value = result })
    .catch(() => { /* 兼容滚动发布期间的旧后端 */ })
})
</script>

<style scoped>
.header-actions { display: flex; gap: 8px; flex-wrap: wrap; }
.rack-body { margin-top: 12px; }
.tree-card { height: 100%; }
.tree-header { display: flex; justify-content: space-between; align-items: center;
  margin-bottom: 8px; }
.tree-title { font-size: 13px; font-weight: 600; }
.rack-tree { max-height: 640px; overflow-y: auto; }
.tree-node { display: flex; align-items: center; gap: 6px; min-width: 0; flex: 1; }
.tree-label { flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.tree-count { color: var(--itsm-text-muted); font-size: 12px; }
.tree-empty { color: var(--itsm-text-muted); text-align: center; padding: 20px 0;
  font-size: 13px; }
.tree-color-dot { width: 10px; height: 10px; border-radius: 3px; display: inline-block;
  flex-shrink: 0; }
.rack-dot { background: var(--el-border-color); }
.w-full { width: 100%; }
.text-muted { color: var(--itsm-text-muted); font-size: 12px; margin-left: 8px; }
.detail-card { min-height: 640px; }
.detail-empty { display: flex; flex-direction: column; align-items: center;
  justify-content: center; min-height: 560px; gap: 8px; }
.empty-icon { color: var(--el-border-color); }
.rack-title-row { display: flex; align-items: center; gap: 8px; margin-bottom: 12px;
  flex-wrap: wrap; }
.rack-name { font-size: 16px; }
.rack-actions { margin-left: auto; display: flex; gap: 8px; flex-wrap: wrap; }
.color-dot { width: 14px; height: 14px; border-radius: 3px; display: inline-block; }
.rack-summary { display: grid; grid-template-columns: repeat(5, minmax(0, 1fr));
  gap: 6px; margin-bottom: 6px; }
.stat-card { background: var(--itsm-card-bg); border: 1px solid var(--itsm-border);
  border-radius: 6px; min-height: 36px; padding: 4px 6px; display: flex;
  align-items: baseline; justify-content: center; gap: 5px; min-width: 0; }
.stat-num { font-size: 14px; font-weight: 600; white-space: nowrap; }
.stat-label { color: var(--itsm-text-muted); font-size: 11px; line-height: 1.2;
  min-width: 0; }
.capacity-status { min-height: 22px; margin-bottom: 6px; display: flex; align-items: center;
  gap: 12px; flex-wrap: wrap; font-size: 11px; }
.capacity-warning { color: var(--el-color-warning); }
.capacity-danger { color: var(--el-color-danger); font-weight: 600; }
.capacity-help { color: var(--itsm-text-muted); display: inline-flex; align-items: center;
  gap: 3px; cursor: help; margin-left: auto; white-space: nowrap; }

/* U 位图 + 设备表左右布局 */
.rack-visual { display: flex; gap: 12px; align-items: flex-start; flex-wrap: wrap; }
.rack-frame { width: 230px; flex-shrink: 0; border: 1px solid var(--itsm-border);
  border-radius: 8px; padding: 6px; }
.rack-frame-header { color: var(--itsm-text-inverse); text-align: center; font-size: 12px; padding: 3px 0;
  border-radius: 4px 4px 0 0; }
.rack-side-switch { display: flex; justify-content: center; padding-top: 5px; }
.rack-u { display: flex; flex-direction: column; gap: 1px; padding: 3px 0; }
.u-row { height: 15px; font-size: 10px; padding: 0 3px; display: flex; align-items: center;
  border-left: 3px solid var(--itsm-border); cursor: default; border-radius: 2px; }
.u-row.empty { background: var(--el-fill-color-light); color: var(--itsm-text-muted); cursor: pointer; }
.u-row.empty:hover { border-left-color: var(--el-color-primary); }
.u-row.installed { color: var(--itsm-text-inverse); cursor: pointer; }
.u-row.installed:hover { filter: brightness(0.9); }
.u-row .u-label { width: 30px; flex-shrink: 0; opacity: 0.75; font-family: var(--font-mono, monospace); }
.u-row .u-content { flex-grow: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.u-sub { margin-left: 6px; opacity: 0.85; }
.rack-frame-hint { text-align: center; font-size: 11px; padding-top: 3px; }
.install-table-wrap { flex: 1; min-width: 420px; overflow-x: auto; }

/* S7-6 窄屏：U 位图占满宽，设备表不强制最小宽（横向滚动） */
@media (max-width: 767px) {
  .rack-summary { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .stat-card { justify-content: flex-start; }
  .rack-frame { width: 100%; }
  .u-row { height: 19px; }
  .install-table-wrap { min-width: 0; }
}
</style>
