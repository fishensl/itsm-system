<template>
  <div class="page-container">
    <div class="page-header">
      <h2 class="page-title">知识库</h2>
      <div class="header-actions">
        <el-button v-if="user.hasPerm('kb:add')" type="primary" :icon="Plus" @click="openCreate">
          新建知识
        </el-button>
      </div>
    </div>

    <!-- 筛选 -->
    <el-card shadow="never" class="filter-card">
      <div class="filter-row">
        <el-input v-model="query.search" placeholder="搜索标题 / 标签" clearable class="filter-search"
          @keyup.enter="reload" @clear="reload" />
        <el-select v-model="query.category" placeholder="分类" clearable class="filter-item" @change="reload">
          <el-option v-for="c in dicts?.categories || []" :key="c" :label="c" :value="c" />
        </el-select>
        <el-select v-model="query.is_published" placeholder="发布状态" clearable class="filter-item" @change="reload">
          <el-option label="已发布" :value="1" />
          <el-option label="未发布" :value="0" />
        </el-select>
        <el-button type="primary" plain :icon="Search" @click="reload">查询</el-button>
      </div>
    </el-card>

    <!-- 列表 -->
    <DataTable
      ref="tableRef"
      :columns="columns"
      :fetch-data="fetchKnowledgeList"
      :query="query"
      row-key="id"
    />

    <!-- 查看正文 -->
    <el-dialog v-model="contentVisible" :title="content?.title || '正文'" width="640px" top="5vh"
      destroy-on-close>
      <div v-if="content">
        <el-descriptions :column="2" border size="small">
          <el-descriptions-item label="分类">
            <el-tag size="small" type="primary">{{ content.category || '未分类' }}</el-tag>
          </el-descriptions-item>
          <el-descriptions-item label="发布状态">
            <el-tag size="small" :type="content.is_published ? 'success' : 'info'">
              {{ content.published_label }}
            </el-tag>
          </el-descriptions-item>
          <el-descriptions-item label="创建人">{{ content.created_by || '-' }}</el-descriptions-item>
          <el-descriptions-item label="创建时间">{{ content.created_at || '-' }}</el-descriptions-item>
          <el-descriptions-item label="查看次数">{{ content.view_count }}</el-descriptions-item>
          <el-descriptions-item label="有用数">{{ content.helpful_count }}</el-descriptions-item>
        </el-descriptions>

        <el-divider content-position="left">标签</el-divider>
        <div v-if="content.tags">
          <el-tag v-for="t in content.tags.split(/[,，\s]+/).filter(Boolean)" :key="t" size="small"
            class="tag-chip" effect="plain">{{ t }}</el-tag>
        </div>
        <p v-else class="detail-text">-</p>

        <el-divider content-position="left">内容</el-divider>
        <div class="kb-content" v-html="content.content || '<p>-</p>'" />
      </div>
    </el-dialog>

    <!-- 附件在线预览（点击列表附件文件名直接打开） -->
    <el-dialog v-model="previewVisible" :title="previewAtt?.file_name || '附件预览'" width="780px" top="5vh"
      destroy-on-close>
      <FilePreview v-if="previewAtt && previewKbId"
        :url="knowledgeAttachmentPreviewUrl(previewKbId, previewAtt.id)"
        :file-name="previewAtt.file_name" />
    </el-dialog>

    <!-- 新建/编辑知识 -->
    <el-dialog v-model="formVisible" :title="form.id ? '编辑知识' : '新建知识'" width="680px" top="5vh"
      destroy-on-close>
      <el-form ref="formRef" :model="form" :rules="formRules" label-width="90px">
        <el-form-item label="标题" prop="title">
          <el-input v-model="form.title" placeholder="必填，如：核心交换机冗余配置故障案例" />
        </el-form-item>
        <el-row :gutter="12">
          <el-col :xs="24" :sm="12">
            <el-form-item label="分类">
              <el-select v-model="form.category" class="w-full">
                <el-option v-for="c in dicts?.categories || []" :key="c" :label="c" :value="c" />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :xs="24" :sm="12">
            <el-form-item label="标签">
              <el-input v-model="form.tags" placeholder="逗号分隔，如：网络,交换机" />
            </el-form-item>
          </el-col>
        </el-row>
        <el-form-item label="内容">
          <el-input v-model="form.content" type="textarea" :rows="10" placeholder="支持 HTML 内容" />
        </el-form-item>
        <el-form-item label="附件">
          <el-upload
            v-model:file-list="pendingFiles"
            :auto-upload="false"
            :multiple="true"
            :limit="10"
            accept=".pdf,.doc,.docx,.xls,.xlsx,.png,.jpg,.jpeg,.gif,.bmp,.webp,.txt"
            :on-exceed="onUploadExceed"
            class="att-upload"
          >
            <el-button :icon="Upload">选择文件</el-button>
            <template #tip>
              <div class="el-upload__tip">PDF/Word/Excel/图片/TXT，最多 10 个（保存时上传）</div>
            </template>
          </el-upload>
          <div v-if="form.id && existingAtts.length" class="att-list form-att-list">
            <div v-for="a in existingAtts" :key="a.id" class="att-item">
              <el-icon :size="16" color="#909399"><Document /></el-icon>
              <span class="att-name">{{ a.file_name }}</span>
              <span class="att-meta">{{ fmtSize(a.file_size) }}</span>
              <el-button size="small" link type="danger" :icon="Delete" @click="onRemoveExisting(a)">
                移除
              </el-button>
            </div>
          </div>
        </el-form-item>
        <el-form-item label="发布">
          <el-switch v-model="form.is_published" active-text="发布" inactive-text="草稿" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="formVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="save">{{ form.id ? '保存' : '创建' }}</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ElMessageBox } from 'element-plus/es/components/message-box/index'
import type { UploadUserFile } from 'element-plus/es/components/upload'
import { ref, reactive, computed, onMounted, watch, h } from 'vue'
import { Plus, Search, Upload, Document, Delete } from '@element-plus/icons-vue'
import { useRoute } from 'vue-router'
import type { UploadRawFile } from 'element-plus/es/components/upload'
import DataTable, { type DataColumn } from '@/components/DataTable.vue'
import FilePreview from '@/components/FilePreview.vue'
import { useUserStore } from '@/stores/user'
import { useUiStore } from '@/stores/ui'
import {
  fetchKnowledgeList, fetchKnowledge, createKnowledge, updateKnowledge, deleteKnowledge,
  fetchKnowledgeDicts, uploadKnowledgeAttachments, deleteKnowledgeAttachment,
  knowledgeAttachmentPreviewUrl, knowledgeAttachmentDownloadUrl,
  KNOWLEDGE_CATEGORY_TAG as CATEGORY_TAG,
  type KnowledgeItem, type KnowledgeDicts, type KnowledgeAttachment,
} from '@/api/knowledge'

const user = useUserStore()
const ui = useUiStore()
const route = useRoute()
const dicts = ref<KnowledgeDicts | null>(null)

const query = reactive<Record<string, unknown>>({ search: '', category: '', is_published: undefined })
const tableRef = ref()

const columns = computed<DataColumn[]>(() => [
  { key: 'title', label: '标题', minWidth: 220, asTitle: true },
  { key: 'category', label: '分类', width: 100, type: 'tag', asTag: true, tagMap: CATEGORY_TAG },
  { key: 'attachments', label: '附件', minWidth: 200, type: 'custom',
    render: (row) => renderAttachments(row) },
  { key: 'view_count', label: '查看数', width: 80 },
  { key: 'helpful_count', label: '有用数', width: 80 },
  { key: 'published_label', label: '发布状态', width: 90, type: 'tag',
    tagMap: { 已发布: 'success', 未发布: 'info' } },
  { key: 'created_by', label: '创建人', width: 100 },
  { key: 'created_at', label: '创建时间', width: 130 },
  { key: 'actions', label: '操作', width: 200, type: 'action', fixed: 'right',
    actions: [
      { label: '查看正文', type: 'primary', link: true, perm: 'kb:view', icon: 'View',
        onClick: (row) => openContent(row as unknown as KnowledgeItem) },
      { label: '编辑', type: 'primary', link: true, perm: 'kb:edit', icon: 'Edit',
        onClick: (row) => openEdit(row as unknown as KnowledgeItem) },
      { label: '删除', type: 'danger', link: true, perm: 'kb:delete', icon: 'Delete',
        onClick: (row) => onDelete(row as unknown as KnowledgeItem) },
    ] },
])

// 查看正文（顺带浏览量 +1）
const contentVisible = ref(false)
const content = ref<KnowledgeItem | null>(null)

async function openContent(row: KnowledgeItem) {
  try {
    content.value = await fetchKnowledge(row.id)
    contentVisible.value = true
  } catch { /* toast */ }
}

async function onDelete(k: KnowledgeItem) {
  try {
    await ElMessageBox.confirm(`确定删除知识「${k.title}」吗？`, '删除确认', { type: 'warning' })
  } catch { return }
  try {
    await deleteKnowledge(k.id)
    ui.toast('已删除', 'success')
    tableRef.value?.refresh()
  } catch (e) {
    ui.toast((e as Error).message, 'error')
  }
}

// 新建/编辑
const formVisible = ref(false)
const saving = ref(false)
const formRef = ref()
const form = reactive<Record<string, unknown>>({
  id: null, title: '', category: '故障案例', tags: '', content: '', is_published: true,
})
const formRules = { title: [{ required: true, message: '请输入标题', trigger: 'blur' }] }

function blankForm() {
  return { id: null, title: '', category: '故障案例', tags: '', content: '', is_published: true }
}

function openCreate() {
  Object.assign(form, blankForm())
  pendingFiles.value = []
  existingAtts.value = []
  formVisible.value = true
}

async function openEdit(k: KnowledgeItem) {
  try {
    const detailData = await fetchKnowledge(k.id)
    Object.assign(form, {
      id: detailData.id, title: detailData.title, category: detailData.category,
      tags: detailData.tags || '', content: detailData.content || '',
      is_published: detailData.is_published,
    })
    pendingFiles.value = []
    existingAtts.value = detailData.attachments || []
    formVisible.value = true
  } catch { /* toast */ }
}

async function save() {
  try { await formRef.value?.validate() } catch { return }
  saving.value = true
  try {
    let kbId = form.id as number | null
    if (kbId) {
      await updateKnowledge(kbId, { ...form })
      ui.toast('已保存', 'success')
    } else {
      const created = await createKnowledge({ ...form })
      kbId = created.id
      ui.toast('知识条目已创建', 'success')
    }
    // 附件：保存后逐批上传待传文件
    const files = pendingFiles.value.map((f) => f.raw).filter((f): f is UploadRawFile => !!f)
    if (files.length && kbId) {
      await uploadKnowledgeAttachments(kbId, files)
    }
    formVisible.value = false
    tableRef.value?.refresh()
  } catch (e) {
    ui.toast((e as Error).message, 'error')
  } finally {
    saving.value = false
  }
}

// ==================== 附件 ====================
function fmtSize(n: number) {
  if (!n) return '-'
  if (n < 1024) return `${n} B`
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`
  return `${(n / 1024 / 1024).toFixed(1)} MB`
}

function openDownload(url: string) {
  window.open(url, '_blank')
}

// 附件在线预览（列表内点击文件名直接打开，不再经过详情抽屉）
const previewVisible = ref(false)
const previewAtt = ref<KnowledgeAttachment | null>(null)
const previewKbId = ref<number | null>(null)

function openPreview(a: KnowledgeAttachment, kbId: number) {
  previewAtt.value = a
  previewKbId.value = kbId
  previewVisible.value = true
}

async function onDeleteAttachment(a: KnowledgeAttachment, kbId: number) {
  try {
    await ElMessageBox.confirm(`确定删除附件「${a.file_name}」吗？`, '删除确认', { type: 'warning' })
  } catch { return }
  try {
    await deleteKnowledgeAttachment(kbId, a.id)
    ui.toast('附件已删除', 'success')
    tableRef.value?.refresh()
  } catch (e) {
    ui.toast((e as Error).message, 'error')
  }
}

/** 附件列自定义渲染：文件名点击预览，行内 下载/删除 */
function renderAttachments(row: Record<string, unknown>) {
  const atts = (row.attachments as KnowledgeAttachment[] | undefined) || []
  if (!atts.length) return '-'
  const kbId = row.id as number
  return h('div', { class: 'att-inline' }, atts.map((a) => h('div', { class: 'att-inline-row' }, [
    h('span', {
      class: 'att-inline-name', title: a.file_name,
      onClick: (e: MouseEvent) => { e.stopPropagation(); openPreview(a, kbId) },
    }, a.file_name),
    h('span', {
      class: 'att-inline-op', title: '下载',
      onClick: (e: MouseEvent) => {
        e.stopPropagation()
        openDownload(knowledgeAttachmentDownloadUrl(kbId, a.id))
      },
    }, '下载'),
    h('span', {
      class: 'att-inline-op att-inline-del', title: '删除',
      onClick: (e: MouseEvent) => { e.stopPropagation(); onDeleteAttachment(a, kbId) },
    }, '删除'),
  ])))
}

// 表单附件：待传列表 + 已有附件
const pendingFiles = ref<UploadUserFile[]>([])
const existingAtts = ref<KnowledgeAttachment[]>([])

function onUploadExceed() {
  ui.toast('最多选择 10 个附件', 'warning')
}

async function onRemoveExisting(a: KnowledgeAttachment) {
  if (!form.id) return
  try {
    await deleteKnowledgeAttachment(form.id as number, a.id)
    existingAtts.value = existingAtts.value.filter((x) => x.id !== a.id)
    ui.toast('附件已移除', 'success')
  } catch (e) {
    ui.toast((e as Error).message, 'error')
  }
}

function reload() { tableRef.value?.refresh() }

// 侧栏分类链接（/app/knowledge-base?category=xxx）自动应用筛选
watch(
  () => route.query.category,
  (cat) => {
    if (cat) {
      query.category = String(cat)
      reload()
    }
  },
)

onMounted(() => {
  fetchKnowledgeDicts().then((d) => (dicts.value = d))
})
</script>

<style scoped>
.filter-card { margin-bottom: 12px; }
.filter-row { display: flex; gap: 8px; flex-wrap: wrap; align-items: center; }
.filter-search { width: 200px; max-width: 100%; }
.filter-item { width: 130px; max-width: 100%; }
.header-actions { display: flex; gap: 8px; flex-wrap: wrap; }
.w-full { width: 100%; }
.detail-text { white-space: pre-wrap; word-break: break-all; font-size: 13px; }
.tag-chip { margin-right: 6px; margin-bottom: 4px; }
.kb-content { font-size: 13px; line-height: 1.7; word-break: break-all; }
.att-list { display: flex; flex-direction: column; gap: 4px; }
.att-item {
  display: flex; align-items: center; gap: 8px; padding: 6px 8px;
  border: 1px solid var(--itsm-border); border-radius: 6px; font-size: 13px;
}
.att-name { font-weight: 500; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; max-width: 240px; }
.att-meta { color: var(--itsm-text-muted); font-size: 12px; }
.att-ops { margin-left: auto; display: flex; gap: 4px; flex-shrink: 0; }
.form-att-list { margin-top: 8px; }
.att-upload { display: block; }
</style>

<!-- 附件列内联渲染（h() VNode 无 scoped 标记，需全局样式） -->
<style>
.att-inline { display: flex; flex-direction: column; gap: 2px; }
.att-inline-row { display: flex; align-items: center; gap: 6px; min-width: 0; }
.att-inline-name {
  cursor: pointer; color: var(--itsm-primary, #2563eb); font-size: 12px;
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis; flex-shrink: 1;
}
.att-inline-name:hover { text-decoration: underline; }
.att-inline-op {
  cursor: pointer; font-size: 11px; color: var(--itsm-text-muted);
  flex-shrink: 0; padding: 0 2px;
}
.att-inline-op:hover { color: var(--itsm-primary, #2563eb); }
.att-inline-del:hover { color: #f56c6c; }
</style>
