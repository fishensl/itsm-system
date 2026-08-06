<template>
  <div class="page-container">
    <div class="page-header">
      <h2 class="page-title">拓扑图</h2>
      <div class="header-actions">
        <el-button v-if="user.hasPerm('topology:add')" type="primary" plain :icon="Plus" @click="openUpload">
          上传拓扑图
        </el-button>
        <el-button v-if="user.hasPerm('topology:add')" type="primary" :icon="EditPen" @click="newDraw">
          在线绘制
        </el-button>
        <el-button :icon="Fold" @click="activeNames = []">收起全部</el-button>
      </div>
    </div>

    <!-- 筛选 -->
    <el-card shadow="never" class="filter-card">
      <div class="filter-row">
        <el-input v-model="query.search" placeholder="搜索名称 / 描述" clearable class="filter-search"
          @keyup.enter="loadAll" @clear="loadAll" />
        <el-button type="primary" plain :icon="Search" :loading="loading" @click="loadAll">查询</el-button>
      </div>
    </el-card>

    <!-- 客户分组手风琴 -->
    <el-card shadow="never" v-loading="loading">
      <el-collapse v-model="activeNames" accordion>
        <el-collapse-item v-for="g in groups" :key="g.customer" :name="g.customer">
          <template #title>
            <span class="grp-title">{{ g.customer }}</span>
            <el-tag size="small" type="info" class="grp-badge">{{ g.rows.length }}</el-tag>
          </template>
          <el-table :data="g.rows" size="small" border stripe>
            <el-table-column label="名称" min-width="260">
              <template #default="{ row }">
                <div class="topo-name-row">
                  <b class="topo-name">{{ row.name }}</b>
                  <span class="topo-icons">
                    <template v-for="f in row.files" :key="f.id">
                      <template v-for="a in fileActions(row, f)" :key="a.key">
                        <el-tooltip :content="a.tip" placement="top">
                          <a v-if="a.href" :href="a.href" :download="a.download ? '' : undefined"
                            target="_blank" class="ficon-link">
                            <el-icon :class="['ficon', a.cls]"><component :is="a.icon" /></el-icon>
                          </a>
                          <span v-else class="ficon-link" @click="a.onClick">
                            <el-icon :class="['ficon', a.cls]"><component :is="a.icon" /></el-icon>
                          </span>
                        </el-tooltip>
                      </template>
                    </template>
                  </span>
                </div>
              </template>
            </el-table-column>
            <el-table-column label="描述" min-width="160">
              <template #default="{ row }">{{ row.description || '-' }}</template>
            </el-table-column>
            <el-table-column label="上传人" width="100">
              <template #default="{ row }">{{ row.upload_by || '-' }}</template>
            </el-table-column>
            <el-table-column label="上传时间" width="140">
              <template #default="{ row }">{{ row.created_at || '-' }}</template>
            </el-table-column>
            <el-table-column label="操作" width="130" fixed="right">
              <template #default="{ row }">
                <el-button v-if="user.hasPerm('topology:edit')" size="small" type="warning" link
                  @click="openEdit(row)">编辑</el-button>
                <el-button v-if="user.hasPerm('topology:delete')" size="small" type="danger" link
                  @click="onDeleteGroup(row)">删除</el-button>
              </template>
            </el-table-column>
            <template #empty>
              <el-empty description="暂无可显示行" :image-size="50" />
            </template>
          </el-table>
        </el-collapse-item>
      </el-collapse>
      <el-empty v-if="!loading && !groups.length" description="暂无拓扑图" :image-size="70" />
    </el-card>

    <!-- 上传弹窗 -->
    <el-dialog v-model="uploadVisible" title="上传拓扑图" width="520px" top="8vh" destroy-on-close>
      <el-form label-width="90px">
        <el-form-item label="拓扑图类型" required>
          <el-select v-model="uploadForm.topo_type" class="w-full" @change="autoName">
            <el-option v-for="t in TOPO_TYPES" :key="t" :label="t" :value="t" />
          </el-select>
        </el-form-item>
        <el-form-item label="名称">
          <el-input v-model="uploadForm.name" placeholder="留空时按「客户+类型+日期」自动拼接"
            @input="nameTouched = true" />
        </el-form-item>
        <el-form-item label="描述">
          <el-input v-model="uploadForm.description" type="textarea" :rows="2" />
        </el-form-item>
        <el-form-item label="客户">
          <el-select v-model="uploadForm.customer_id" clearable filterable class="w-full" @change="autoName">
            <el-option v-for="c in dicts?.customers || []" :key="c.id" :label="c.name" :value="c.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="地区">
          <el-select v-model="uploadForm.region_id" clearable filterable class="w-full">
            <el-option v-for="r in dicts?.regions || []" :key="r.id" :label="r.name" :value="r.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="文件" required>
          <input ref="fileInput" type="file" class="el-input__inner file-input"
            accept=".jpg,.jpeg,.png,.gif,.bmp,.pdf,.vsd,.vsdx,.drawio,.xml" @change="onFileChange" />
          <div class="text-muted">支持 JPG/PNG/PDF/Visio/drawio 文件</div>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="uploadVisible = false">取消</el-button>
        <el-button type="primary" :loading="uploading" @click="saveUpload">上传</el-button>
      </template>
    </el-dialog>

    <!-- 编辑弹窗 -->
    <el-dialog v-model="editVisible" :title="`编辑「${editForm.name || ''}」`" width="520px" top="8vh"
      destroy-on-close>
      <el-form ref="editFormRef" :model="editForm" :rules="editFormRules" label-width="90px">
        <el-form-item label="名称" prop="name">
          <el-input v-model="editForm.name" />
        </el-form-item>
        <el-form-item label="描述">
          <el-input v-model="editForm.description" type="textarea" :rows="2" />
        </el-form-item>
        <el-form-item label="客户">
          <el-select v-model="editForm.customer_id" clearable filterable class="w-full">
            <el-option v-for="c in dicts?.customers || []" :key="c.id" :label="c.name" :value="c.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="地区">
          <el-select v-model="editForm.region_id" clearable filterable class="w-full">
            <el-option v-for="r in dicts?.regions || []" :key="r.id" :label="r.name" :value="r.id" />
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="editVisible = false">取消</el-button>
        <el-button type="primary" :loading="editing" @click="saveEdit">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ElMessageBox } from 'element-plus/es/components/message-box/index'
import { ref, reactive, onMounted, type Component } from 'vue'
import { Search, EditPen, Plus, Fold, Picture, Document, Files } from '@element-plus/icons-vue'
import { useUserStore } from '@/stores/user'
import { useUiStore } from '@/stores/ui'
import {
  fetchTopologies, fetchTopology, updateTopology, deleteTopology,
  fetchTopologyDicts, uploadTopology,
  type TopologyItem, type TopologyFile, type TopologyDicts,
} from '@/api/topology'

const user = useUserStore()
const ui = useUiStore()

const TOPO_TYPES = ['网络拓扑图', '会议室拓扑图', '业务拓扑图', '机房拓扑图', '存储拓扑图', '安全拓扑图']

interface TopoGroup {
  customer: string
  rows: TopologyItem[]
}

interface FileAction {
  key: string
  icon: Component
  cls: string
  tip: string
  href?: string
  download?: boolean
  onClick?: () => void
}

const query = reactive<Record<string, unknown>>({ search: '' })
const groups = ref<TopoGroup[]>([])
const activeNames = ref<string[]>([])
const loading = ref(false)

async function loadAll() {
  loading.value = true
  try {
    const first = await fetchTopologies({ search: query.search, page: 1, page_size: 100 })
    const pageCount = Math.max(1, Math.ceil(first.total / 100))
    const pages = await Promise.all(
      Array.from({ length: pageCount - 1 }, (_, i) =>
        fetchTopologies({ search: query.search, page: i + 2, page_size: 100 })),
    )
    const all = [first, ...pages].flatMap((res) => res.items)
    const map = new Map<string, TopologyItem[]>()
    for (const item of all) {
      const key = item.customer_name
      if (!map.has(key)) map.set(key, [])
      map.get(key)!.push(item)
    }
    const names = [...map.keys()].sort(
      (a, b) => (a === '未关联客户' ? 1 : b === '未关联客户' ? -1 : a.localeCompare(b, 'zh')))
    groups.value = names.map((n) => ({ customer: n, rows: map.get(n)! }))
    if (names.length && !activeNames.value.length) activeNames.value = [names[0]]
  } catch (e) {
    ui.toast((e as Error).message, 'error')
  } finally {
    loading.value = false
  }
}

// ==================== 文件图标行为矩阵（对齐 SSR 列表） ====================
function openEditor(id: number) {
  window.open(`/topologies/editor/${id}`, '_blank')
}

function newDraw() {
  window.open('/topologies/editor/0', '_blank')
}

function importEdit(f: TopologyFile) {
  window.open(`/topologies/editor/0?import=${f.id}`, '_blank')
}

function fileActions(row: TopologyItem, f: TopologyFile): FileAction[] {
  const acts: FileAction[] = []
  if (f.source === 'draw') {
    acts.push({ key: 'edit', icon: EditPen, cls: 'fi-edit',
      tip: '在线拓扑图 — 点击编辑', onClick: () => openEditor(f.id) })
    if (f.thumbnail) acts.push({ key: 'png', icon: Picture, cls: 'fi-png',
      tip: 'PNG 缩略图 — 点击预览', href: f.thumbnail })
    if (f.svg) acts.push({ key: 'svg', icon: Document, cls: 'fi-svg',
      tip: 'SVG 矢量图 — 点击预览', href: f.svg })
    acts.push({ key: 'drawio', icon: Files, cls: 'fi-drawio',
      tip: 'drawio 格式 — 新版 Visio 可直接打开',
      href: `/topologies/download/drawio/${f.id}`, download: true })
    if (f.pdf) acts.push({ key: 'pdf', icon: Document, cls: 'fi-pdf',
      tip: 'PDF（自动生成）— 点击预览', href: f.pdf })
    if (f.vsdx) acts.push({ key: 'vsdx', icon: Files, cls: 'fi-vsdx',
      tip: 'Visio（自动生成）— 点击下载', href: f.vsdx, download: true })
  } else if (f.file_type === 'pdf') {
    acts.push({ key: 'pdf', icon: Document, cls: 'fi-pdf',
      tip: '点击预览 PDF', href: f.url })
  } else if (f.file_type === 'visio') {
    acts.push({ key: 'visio', icon: Files, cls: 'fi-visio',
      tip: '点击下载 Visio 文件', href: f.url, download: true })
    if (user.hasPerm('topology:add')) acts.push({ key: 'import', icon: EditPen, cls: 'fi-import',
      tip: '导入此 Visio 文件在线编辑（Visio 导入较慢，建议先转为 .drawio 格式）',
      onClick: () => importEdit(f) })
  } else if (f.file_type === 'drawio') {
    acts.push({ key: 'drawio', icon: Files, cls: 'fi-drawio',
      tip: '点击下载 drawio 文件', href: f.url, download: true })
    if (user.hasPerm('topology:add')) acts.push({ key: 'import', icon: EditPen, cls: 'fi-import',
      tip: '导入此 drawio 文件在线编辑（另存为新在线图）', onClick: () => importEdit(f) })
  } else if (f.file_type === 'image') {
    acts.push({ key: 'image', icon: Picture, cls: 'fi-image',
      tip: '点击预览图片', href: f.url })
    if (user.hasPerm('topology:add')) acts.push({ key: 'import', icon: EditPen, cls: 'fi-import',
      tip: '以此图为底图在线绘制（另存为新在线图）', onClick: () => importEdit(f) })
  } else {
    acts.push({ key: 'other', icon: Document, cls: 'fi-other',
      tip: '点击下载', href: f.url, download: true })
  }
  return acts
}

// ==================== 上传 ====================
const uploadVisible = ref(false)
const uploading = ref(false)
const uploadForm = reactive({
  topo_type: TOPO_TYPES[0], name: '', description: '',
  customer_id: null as number | null, region_id: null as number | null,
})
const nameTouched = ref(false)
const fileInput = ref<HTMLInputElement>()
const uploadFile = ref<File | null>(null)

function openUpload() {
  Object.assign(uploadForm, {
    topo_type: TOPO_TYPES[0], name: '', description: '',
    customer_id: null, region_id: null,
  })
  nameTouched.value = false
  uploadFile.value = null
  if (fileInput.value) fileInput.value.value = ''
  uploadVisible.value = true
  autoName()
}

function onFileChange(e: Event) {
  const input = e.target as HTMLInputElement
  uploadFile.value = input.files?.[0] || null
}

function autoName() {
  if (nameTouched.value) return
  const cust = dicts.value?.customers.find((c) => c.id === uploadForm.customer_id)
  const d = new Date()
  const ymd = `${d.getFullYear()}${String(d.getMonth() + 1).padStart(2, '0')}${String(d.getDate()).padStart(2, '0')}`
  uploadForm.name = `${cust ? cust.name : ''}${uploadForm.topo_type}${ymd}`
}

async function saveUpload() {
  const f = uploadFile.value
  if (!f) {
    ui.toast('请选择文件', 'error')
    return
  }
  if (!uploadForm.topo_type) {
    ui.toast('请选择拓扑图类型', 'error')
    return
  }
  uploading.value = true
  try {
    const fd = new FormData()
    fd.append('topo_file', f)
    fd.append('topo_type', uploadForm.topo_type)
    fd.append('name', uploadForm.name)
    fd.append('description', uploadForm.description)
    if (uploadForm.customer_id) fd.append('customer_id', String(uploadForm.customer_id))
    if (uploadForm.region_id) fd.append('region_id', String(uploadForm.region_id))
    await uploadTopology(fd)
    ui.toast('上传成功', 'success')
    uploadVisible.value = false
    loadAll()
  } catch (e) {
    ui.toast((e as Error).message, 'error')
  } finally {
    uploading.value = false
  }
}

// ==================== 编辑 / 删除 ====================
const editVisible = ref(false)
const editing = ref(false)
const editFormRef = ref()
const editForm = reactive({
  id: null as number | null, name: '', description: '',
  customer_id: null as number | null, region_id: null as number | null,
})
const editFormRules = {
  name: [{ required: true, message: '请输入名称', trigger: 'blur' }],
}

async function openEdit(row: TopologyItem) {
  try {
    const d = await fetchTopology(row.id)
    Object.assign(editForm, {
      id: d.id, name: d.name, description: d.description,
      customer_id: d.customer_id, region_id: d.region_id,
    })
    editVisible.value = true
  } catch (e) {
    ui.toast((e as Error).message, 'error')
  }
}

async function saveEdit() {
  try { await editFormRef.value?.validate() } catch { return }
  editing.value = true
  try {
    await updateTopology(editForm.id as number, {
      name: editForm.name,
      description: editForm.description,
      customer_id: editForm.customer_id,
      region_id: editForm.region_id,
    })
    ui.toast('保存成功', 'success')
    editVisible.value = false
    loadAll()
  } catch (e) {
    ui.toast((e as Error).message, 'error')
  } finally {
    editing.value = false
  }
}

async function onDeleteGroup(row: TopologyItem) {
  const ids = row.files.map((f) => f.id)
  const msg = ids.length === 1
    ? `确定删除拓扑图「${row.name}」？`
    : `拓扑图「${row.name}」共 ${ids.length} 个文件，确定全部删除？`
  try {
    await ElMessageBox.confirm(msg, '删除确认', { type: 'warning' })
  } catch { return }
  try {
    for (const id of ids) await deleteTopology(id)
    ui.toast('已删除', 'success')
    loadAll()
  } catch (e) {
    ui.toast((e as Error).message, 'error')
  }
}

// ==================== 字典 ====================
const dicts = ref<TopologyDicts | null>(null)

onMounted(() => {
  fetchTopologyDicts().then((d) => (dicts.value = d)).catch(() => { /* toast */ })
  loadAll()
})
</script>

<style scoped>
.filter-card { margin-bottom: 12px; }
.filter-row { display: flex; gap: 8px; flex-wrap: wrap; align-items: center; }
.filter-search { width: 240px; max-width: 100%; }
.header-actions { display: flex; gap: 8px; flex-wrap: wrap; }
.w-full { width: 100%; }
.text-muted { color: var(--itsm-text-muted); font-size: 12px; }
.file-input { padding: 4px 8px; height: auto; }
.grp-title { font-weight: 600; font-size: 14px; }
.grp-badge { margin-left: 8px; }
.topo-name-row { display: flex; align-items: center; gap: 10px; min-width: 0; }
.topo-name { flex-shrink: 0; }
.topo-icons { display: inline-flex; align-items: center; gap: 4px; flex-wrap: wrap; }
.ficon-link { display: inline-flex; align-items: center; cursor: pointer;
  line-height: 1; }
.ficon { font-size: 15px; }
.fi-edit { color: var(--el-color-primary); }
.fi-png, .fi-image { color: var(--el-color-success); }
.fi-svg { color: var(--el-color-info); }
.fi-drawio { color: var(--el-color-warning); }
.fi-pdf { color: var(--el-color-danger); }
.fi-vsdx { color: var(--el-color-primary); }
.fi-visio { color: var(--el-color-primary); }
.fi-other { color: var(--el-color-info); }
.fi-import { color: var(--el-color-info); }
</style>
