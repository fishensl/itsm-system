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
      </div>
    </div>

    <!-- 筛选 -->
    <el-card shadow="never" class="filter-card">
      <div class="filter-row">
        <el-input v-model="query.search" placeholder="搜索名称 / 描述" clearable class="filter-search"
          @keyup.enter="reload" @clear="reload" />
        <el-button type="primary" plain :icon="Search" @click="reload">查询</el-button>
      </div>
    </el-card>

    <!-- 列表 -->
    <DataTable
      ref="tableRef"
      :columns="columns"
      :fetch-data="fetchTopologies"
      :query="query"
      row-key="id"
      @row-click="openDetail"
    />

    <!-- 详情弹窗 -->
    <el-dialog v-model="detailVisible" :title="detail?.name || '拓扑图详情'" width="640px" top="6vh"
      destroy-on-close>
      <div v-if="detail">
        <el-descriptions :column="2" border size="small">
          <el-descriptions-item label="客户">{{ detail.customer_name }}</el-descriptions-item>
          <el-descriptions-item label="地区">{{ detail.region_name || '-' }}</el-descriptions-item>
          <el-descriptions-item label="来源">
            <el-tag size="small" :type="detail.source === 'draw' ? 'primary' : 'info'">
              {{ detail.source === 'draw' ? '在线绘制' : '文件上传' }}
            </el-tag>
          </el-descriptions-item>
          <el-descriptions-item label="文件数">{{ detail.file_count }}</el-descriptions-item>
        </el-descriptions>
        <p v-if="detail.description" class="detail-text">{{ detail.description }}</p>

        <el-divider content-position="left">关联文件</el-divider>
        <div v-for="f in detail.files" :key="f.id" class="file-item">
          <el-tag size="small" :type="TOPOLOGY_TYPE_TAG[f.file_type] || 'info'" class="file-tag">
            {{ f.file_type }}
          </el-tag>
          <span class="file-name">{{ f.file_path || `#${f.id}（在线图）` }}</span>
          <span v-if="f.upload_by" class="text-muted">上传：{{ f.upload_by }}</span>
          <div class="file-actions">
            <el-button v-if="f.url" size="small" type="primary" link :href="f.url" target="_blank">
              打开
            </el-button>
            <el-button v-if="f.pdf" size="small" type="primary" link :href="f.pdf" target="_blank">
              PDF
            </el-button>
            <el-button v-if="f.vsdx" size="small" type="primary" link :href="f.vsdx" target="_blank">
              VSDX
            </el-button>
            <el-button v-if="f.svg" size="small" type="primary" link :href="f.svg" target="_blank">
              SVG
            </el-button>
            <el-button v-if="f.file_type === 'drawio'" size="small" type="primary" link
              :href="`/topologies/download/drawio/${f.id}`" target="_blank">
              drawio
            </el-button>
            <el-button v-if="isImportable(f)" size="small" type="success" link @click="importEdit(f)">
              导入后编辑
            </el-button>
            <el-button v-if="user.hasPerm('topology:delete')" size="small" type="danger" link
              @click="onDeleteFile(f)">
              删除
            </el-button>
          </div>
        </div>
        <el-empty v-if="!detail.files.length" description="暂无文件" :image-size="50" />

        <el-divider content-position="left">在线编辑</el-divider>
        <div class="editor-row">
          <template v-if="detail.has_editor">
            <el-button type="primary" :icon="EditPen" @click="openEditor">打开编辑器</el-button>
            <span v-if="detail.source !== 'draw'" class="text-muted">
              该拓扑图为上传文件导入生成的在线图
            </span>
          </template>
          <el-alert v-else type="info" :closable="false"
            title="该拓扑图暂无在线图；可通过上方「导入后编辑」或「在线绘制」创建。" />
        </div>
      </div>
    </el-dialog>

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
import { ref, reactive, computed, onMounted } from 'vue'
import { ElMessageBox } from 'element-plus'
import { Search, EditPen, Plus } from '@element-plus/icons-vue'
import DataTable, { type DataColumn } from '@/components/DataTable.vue'
import { useUserStore } from '@/stores/user'
import { useUiStore } from '@/stores/ui'
import {
  fetchTopologies, fetchTopology, updateTopology, deleteTopology,
  fetchTopologyDicts, uploadTopology, TOPOLOGY_TYPE_TAG,
  type TopologyDetail, type TopologyFile, type TopologyDicts,
} from '@/api/topology'

const user = useUserStore()
const ui = useUiStore()

const TOPO_TYPES = ['网络拓扑图', '会议室拓扑图', '业务拓扑图', '机房拓扑图', '存储拓扑图', '安全拓扑图']
const IMPORTABLE_TYPES = ['image', 'visio', 'drawio']

const query = reactive<Record<string, unknown>>({ search: '' })
const tableRef = ref()
const dicts = ref<TopologyDicts | null>(null)

const columns = computed<DataColumn[]>(() => [
  { key: 'name', label: '名称', minWidth: 180, asTitle: true },
  { key: 'customer_name', label: '客户', minWidth: 120 },
  { key: 'type', label: '类型', width: 90, type: 'tag', asTag: true,
    tagMap: TOPOLOGY_TYPE_TAG },
  { key: 'file_count', label: '文件数', width: 80, align: 'center' },
  { key: 'source', label: '来源', width: 90,
    cellClass: (r) => (r.source === 'draw' ? 'source-draw' : '') },
  { key: 'updated_at', label: '更新时间', width: 140 },
  { key: 'actions', label: '操作', width: 160, type: 'action', fixed: 'right',
    actions: [
      { label: '详情', type: 'primary', link: true, perm: 'topology:view', icon: 'View',
        onClick: (row) => openDetail(row) },
      { label: '编辑', type: 'warning', link: true, perm: 'topology:edit', icon: 'Edit',
        onClick: (row) => openEdit(row) },
      { label: '删除', type: 'danger', link: true, perm: 'topology:delete', icon: 'Delete',
        onClick: (row) => onDeleteGroup(row) },
    ] },
])

const detailVisible = ref(false)
const detail = ref<TopologyDetail | null>(null)

async function openDetail(row: Record<string, unknown>) {
  try {
    detail.value = await fetchTopology(row.id as number)
    detailVisible.value = true
  } catch { /* toast */ }
}

function isImportable(f: TopologyFile) {
  return f.source !== 'draw' && IMPORTABLE_TYPES.includes(f.file_type)
}

function openEditor() {
  if (!detail.value) return
  window.open(`/topologies/editor/${detail.value.editor_id}`, '_blank')
}

function newDraw() {
  window.open('/topologies/editor/0', '_blank')
}

function importEdit(f: TopologyFile) {
  window.open(`/topologies/editor/0?import=${f.id}`, '_blank')
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
    reload()
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

async function openEdit(row: Record<string, unknown>) {
  try {
    const d = await fetchTopology(row.id as number)
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
    if (detail.value?.id === editForm.id) detail.value = await fetchTopology(editForm.id)
    reload()
  } catch (e) {
    ui.toast((e as Error).message, 'error')
  } finally {
    editing.value = false
  }
}

async function deleteTopoIds(ids: number[], name: string) {
  const msg = ids.length === 1
    ? `确定删除拓扑图「${name}」？`
    : `拓扑图「${name}」共 ${ids.length} 个文件，确定全部删除？`
  try {
    await ElMessageBox.confirm(msg, '删除确认', { type: 'warning' })
  } catch { return }
  try {
    for (const id of ids) await deleteTopology(id)
    ui.toast('已删除', 'success')
    if (detail.value && ids.includes(detail.value.id)) detailVisible.value = false
    reload()
  } catch (e) {
    ui.toast((e as Error).message, 'error')
  }
}

async function onDeleteGroup(row: Record<string, unknown>) {
  try {
    const d = await fetchTopology(row.id as number)
    await deleteTopoIds(d.files.map((f) => f.id), d.name)
  } catch (e) {
    ui.toast((e as Error).message, 'error')
  }
}

async function onDeleteFile(f: TopologyFile) {
  try {
    await ElMessageBox.confirm(`确定删除该文件（#${f.id}）？`, '删除确认', { type: 'warning' })
  } catch { return }
  try {
    await deleteTopology(f.id)
    ui.toast('已删除', 'success')
    if (detail.value) detail.value = await fetchTopology(detail.value.id)
    reload()
  } catch (e) {
    ui.toast((e as Error).message, 'error')
  }
}

function reload() { tableRef.value?.refresh() }

onMounted(() => {
  fetchTopologyDicts().then((d) => (dicts.value = d)).catch(() => { /* toast */ })
})
</script>

<style scoped>
.filter-card { margin-bottom: 12px; }
.filter-row { display: flex; gap: 8px; flex-wrap: wrap; align-items: center; }
.filter-search { width: 240px; max-width: 100%; }
.header-actions { display: flex; gap: 8px; flex-wrap: wrap; }
.w-full { width: 100%; }
.detail-text { white-space: pre-wrap; word-break: break-all; font-size: 13px;
  margin: 10px 0 0; }
.text-muted { color: var(--itsm-text-muted); font-size: 12px; }
.source-draw { color: var(--el-color-primary); font-weight: 500; }
.file-item { display: flex; align-items: center; gap: 8px; flex-wrap: wrap;
  padding: 8px 10px; border: 1px solid var(--itsm-border); border-radius: 8px; margin-bottom: 8px; }
.file-tag { flex-shrink: 0; text-transform: uppercase; }
.file-name { font-family: var(--font-mono, monospace); font-size: 12px;
  word-break: break-all; min-width: 0; }
.file-actions { display: flex; gap: 4px; margin-left: auto; flex-wrap: wrap; }
.editor-row { display: flex; align-items: center; gap: 10px; }
.file-input { padding: 4px 8px; height: auto; }
</style>
