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

    <!-- 左侧：地市 → 客户 → 机柜 树 + 右侧：内联详情 -->
    <el-row :gutter="12" class="rack-body">
      <el-col :xs="24" :md="6">
        <el-card shadow="never" class="tree-card">
          <div class="tree-header">
            <span class="tree-title">机柜（按地市）</span>
            <el-button size="small" text :icon="Refresh" @click="loadTree" />
          </div>
          <el-tree
            :data="treeData"
            node-key="id"
            :props="{ label: 'label', children: 'children' }"
            :expand-on-click-node="false"
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
            <el-row :gutter="8" class="stat-row">
              <el-col :xs="12" :sm="8"><div class="stat-card"><div class="stat-num">{{ detail.total_u }}U</div><div class="stat-label">总U位</div></div></el-col>
              <el-col :xs="12" :sm="8"><div class="stat-card"><div class="stat-num">{{ detail.used_label }}</div><div class="stat-label">已占用</div></div></el-col>
              <el-col :xs="12" :sm="8"><div class="stat-card"><div class="stat-num">{{ detail.used_pct }}%</div><div class="stat-label">占用率</div></div></el-col>
              <el-col :xs="12" :sm="8"><div class="stat-card"><div class="stat-num">{{ detail.install_count }}</div><div class="stat-label">安装数</div></div></el-col>
              <el-col :xs="12" :sm="8"><div class="stat-card"><div class="stat-num">{{ detail.used_w }}W</div><div class="stat-label">当前功耗</div></div></el-col>
              <el-col :xs="12" :sm="8"><div class="stat-card"><div class="stat-num">{{ detail.pdu_total_w }}W</div><div class="stat-label">PDU额定</div></div></el-col>
            </el-row>

            <!-- U 位图 + 设备表（左右布局） -->
            <div class="rack-visual">
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
                <div class="rack-frame-hint text-muted">点击空位上架 / 点击设备调整</div>
              </div>

              <div class="install-table-wrap">
                <el-table :data="detail.installs" size="small" border stripe>
                  <el-table-column label="U位" width="90" align="center">
                    <template #default="{ row }">{{ row.start_u }}-{{ row.start_u + row.occupy_u - 1 }}U</template>
                  </el-table-column>
                  <el-table-column label="名称" min-width="140" prop="name" show-overflow-tooltip />
                  <el-table-column label="品牌型号" min-width="120">
                    <template #default="{ row }">
                      {{ [row.brand, row.model].filter(Boolean).join(' ') || '-' }}
                    </template>
                  </el-table-column>
                  <el-table-column label="IP" min-width="110" prop="ip" show-overflow-tooltip />
                  <el-table-column label="来源" width="70" align="center">
                    <template #default="{ row }">
                      <el-tag size="small" :type="row.kind === '托管' ? 'primary' : 'warning'">
                        {{ row.kind }}
                      </el-tag>
                    </template>
                  </el-table-column>
                  <el-table-column label="功耗" width="70" align="right" prop="rated_w" />
                  <el-table-column label="操作" width="110" fixed="right">
                    <template #default="{ row }">
                      <el-button v-if="user.hasPerm('device:edit')" size="small" type="primary" link
                        @click="openAdjust(row)">调整</el-button>
                      <el-button v-if="user.hasPerm('device:delete')" size="small" type="danger" link
                        @click="onUninstall(row)">下架</el-button>
                    </template>
                  </el-table-column>
                  <template #empty>
                    <el-empty description="暂无上架设备" :image-size="50" />
                  </template>
                </el-table>
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
        <el-form-item label="名称" prop="name">
          <el-input v-model="rackForm.name" placeholder="如：A-01" />
        </el-form-item>
        <el-form-item label="所属客户" prop="customer_id">
          <el-select v-model="rackForm.customer_id" filterable class="w-full">
            <el-option v-for="c in dicts?.customers || []" :key="c.id" :label="c.name" :value="c.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="机房位置">
          <el-input v-model="rackForm.location" placeholder="如：2F 机房 B 区" />
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
import { ElMessageBox } from 'element-plus/es/components/message-box/index'
import { ref, reactive, computed, onMounted } from 'vue'
import { Plus, Refresh, Edit, Delete, Collection } from '@element-plus/icons-vue'
import { useUserStore } from '@/stores/user'
import { useUiStore } from '@/stores/ui'
import {
  fetchRack, createRack, updateRack, deleteRack,
  fetchRackDevices, createInstall, updateInstall, deleteInstall, fetchRackDicts,
  fetchRackTree,
  type RackDetail, type RackInstall, type RackDevice, type RackDicts,
} from '@/api/rack'

const user = useUserStore()
const ui = useUiStore()
const dicts = ref<RackDicts | null>(null)

// ==================== 地市 → 客户 → 机柜 树 ====================
interface TreeNode {
  id: string
  label: string
  type: 'city' | 'customer' | 'rack'
  color?: string
  install_count?: number
  children?: TreeNode[]
}

const treeData = ref<TreeNode[]>([])
const expandedKeys = ref<string[]>([])
const currentNodeKey = ref<string>('')

async function loadTree() {
  try {
    const cities = await fetchRackTree()
    const nodes: TreeNode[] = []
    for (const city of cities) {
      const custNodes: TreeNode[] = city.customers.map((c) => ({
        id: `cust-${c.id}`,
        label: `${c.name}（${c.racks.length}）`,
        type: 'customer',
        children: c.racks.map((r) => ({
          id: `rack-${r.id}`,
          label: `${r.name} · ${r.total_u}U`,
          type: 'rack',
          color: r.color,
          install_count: r.install_count,
        })),
      }))
      nodes.push({
        id: `city-${city.city}`,
        label: `${city.city}（${custNodes.length}）`,
        type: 'city',
        children: custNodes,
      })
    }
    treeData.value = nodes
    expandedKeys.value = nodes.filter((n) => n.type === 'city').map((n) => n.id)
  } catch { /* toast */ }
}

function onTreeClick(node: TreeNode) {
  if (node.type === 'rack') {
    selectRack(Number(node.id.split('-')[1]))
  }
}

// ==================== 内联详情 + U 位可视化 ====================
const detail = ref<RackDetail | null>(null)

async function selectRack(id: number) {
  try {
    detail.value = await fetchRack(id)
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

async function openInstall(startU = 1) {
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
    if (detail.value) detail.value = await fetchRack(detail.value.id)
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
.stat-row { margin-bottom: 4px; }
.stat-card { background: var(--itsm-card-bg); border: 1px solid var(--itsm-border);
  border-radius: 8px; padding: 8px 10px; margin-bottom: 8px; }
.stat-num { font-size: 15px; font-weight: 600; }
.stat-label { color: var(--itsm-text-muted); font-size: 12px; }

/* U 位图 + 设备表左右布局 */
.rack-visual { display: flex; gap: 16px; align-items: flex-start; flex-wrap: wrap; }
.rack-frame { width: 280px; flex-shrink: 0; border: 1px solid var(--itsm-border);
  border-radius: 8px; padding: 8px; }
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
.rack-frame-hint { text-align: center; font-size: 12px; padding-top: 4px; }
.install-table-wrap { flex: 1; min-width: 420px; overflow-x: auto; }

/* S7-6 窄屏：U 位图占满宽，设备表不强制最小宽（横向滚动） */
@media (max-width: 767px) {
  .rack-frame { width: 100%; }
  .install-table-wrap { min-width: 0; }
}
</style>
