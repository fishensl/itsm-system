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
      @row-click="openDetail"
    />

    <!-- 详情抽屉 -->
    <el-drawer v-model="detailVisible" :title="detail ? `#${detail.id} · ${detail.title}` : ''"
      size="620px" destroy-on-close>
      <div v-if="detail">
        <el-descriptions :column="2" border size="small">
          <el-descriptions-item label="分类">
            <el-tag size="small" type="primary">{{ detail.category || '未分类' }}</el-tag>
          </el-descriptions-item>
          <el-descriptions-item label="发布状态">
            <el-tag size="small" :type="detail.is_published ? 'success' : 'info'">
              {{ detail.published_label }}
            </el-tag>
          </el-descriptions-item>
          <el-descriptions-item label="创建人">{{ detail.created_by || '-' }}</el-descriptions-item>
          <el-descriptions-item label="创建时间">{{ detail.created_at || '-' }}</el-descriptions-item>
          <el-descriptions-item label="查看次数">{{ detail.view_count }}</el-descriptions-item>
          <el-descriptions-item label="有用数">{{ detail.helpful_count }}</el-descriptions-item>
        </el-descriptions>

        <el-divider content-position="left">标签</el-divider>
        <div v-if="detail.tags">
          <el-tag v-for="t in detail.tags.split(/[,，\s]+/).filter(Boolean)" :key="t" size="small"
            class="tag-chip" effect="plain">{{ t }}</el-tag>
        </div>
        <p v-else class="detail-text">-</p>

        <el-divider content-position="left">内容</el-divider>
        <div class="kb-content" v-html="detail.content || '<p>-</p>'" />
      </div>
    </el-drawer>

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
import { ref, reactive, computed, onMounted, watch } from 'vue'
import { ElMessageBox } from 'element-plus'
import { Plus, Search } from '@element-plus/icons-vue'
import { useRoute } from 'vue-router'
import DataTable, { type DataColumn } from '@/components/DataTable.vue'
import { useUserStore } from '@/stores/user'
import { useUiStore } from '@/stores/ui'
import {
  fetchKnowledgeList, fetchKnowledge, createKnowledge, updateKnowledge, deleteKnowledge,
  fetchKnowledgeDicts, KNOWLEDGE_CATEGORY_TAG as CATEGORY_TAG,
  type KnowledgeItem, type KnowledgeDicts,
} from '@/api/knowledge'

const user = useUserStore()
const ui = useUiStore()
const route = useRoute()
const dicts = ref<KnowledgeDicts | null>(null)

const query = reactive<Record<string, unknown>>({ search: '', category: '', is_published: undefined })
const tableRef = ref()

const columns = computed<DataColumn[]>(() => [
  { key: 'title', label: '标题', type: 'link', minWidth: 220, asTitle: true,
    link: (r) => `/app/knowledge-base/${r.id}` },
  { key: 'category', label: '分类', width: 100, type: 'tag', asTag: true, tagMap: CATEGORY_TAG },
  { key: 'view_count', label: '查看数', width: 80 },
  { key: 'helpful_count', label: '有用数', width: 80 },
  { key: 'published_label', label: '发布状态', width: 90, type: 'tag',
    tagMap: { 已发布: 'success', 未发布: 'info' } },
  { key: 'created_by', label: '创建人', width: 100 },
  { key: 'created_at', label: '创建时间', width: 130 },
  { key: 'actions', label: '操作', width: 140, type: 'action', fixed: 'right',
    actions: [
      { label: '查看', type: 'primary', link: true, perm: 'kb:view', icon: 'View',
        onClick: (row) => openDetail(row) },
      { label: '编辑', type: 'primary', link: true, perm: 'kb:edit', icon: 'Edit',
        onClick: (row) => openEdit(row as unknown as KnowledgeItem) },
      { label: '删除', type: 'danger', link: true, perm: 'kb:delete', icon: 'Delete',
        onClick: (row) => onDelete(row as unknown as KnowledgeItem) },
    ] },
])

// 详情
const detailVisible = ref(false)
const detail = ref<KnowledgeItem | null>(null)

async function openDetail(row: Record<string, unknown>) {
  try {
    detail.value = await fetchKnowledge(row.id as number)
    detailVisible.value = true
  } catch { /* toast */ }
}

async function onDelete(k: KnowledgeItem) {
  try {
    await ElMessageBox.confirm(`确定删除知识「${k.title}」吗？`, '删除确认', { type: 'warning' })
  } catch { return }
  try {
    await deleteKnowledge(k.id)
    ui.toast('已删除', 'success')
    detailVisible.value = false
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
    formVisible.value = true
  } catch { /* toast */ }
}

async function save() {
  try { await formRef.value?.validate() } catch { return }
  saving.value = true
  try {
    if (form.id) {
      await updateKnowledge(form.id as number, { ...form })
      ui.toast('已保存', 'success')
    } else {
      await createKnowledge({ ...form })
      ui.toast('知识条目已创建', 'success')
    }
    formVisible.value = false
    tableRef.value?.refresh()
  } catch (e) {
    ui.toast((e as Error).message, 'error')
  } finally {
    saving.value = false
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
</style>
