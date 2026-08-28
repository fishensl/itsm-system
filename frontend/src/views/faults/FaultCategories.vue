<template>
  <div>
    <div class="cat-toolbar">
      <el-button v-if="user.hasPerm('fault:edit')" type="primary" :icon="Plus" @click="openCreate()">
        新增一级分类
      </el-button>
    </div>

    <el-tree
      v-loading="loading"
      :data="tree"
      node-key="id"
      default-expand-all
      :expand-on-click-node="false"
      :draggable="user.hasPerm('fault:edit')"
      :allow-drop="allowDrop"
      @node-drop="onNodeDrop"
      class="cat-tree"
    >
      <template #default="{ data }">
        <div class="cat-node">
          <el-tag size="small" :type="levelTag(data.level)" effect="plain" class="cat-level">
            {{ ['', '一级', '二级', '三级'][data.level] || '分类' }}
          </el-tag>
          <span class="cat-name">{{ data.name }}</span>
          <span class="cat-actions">
            <el-button v-if="user.hasPerm('fault:edit')" size="small" link
              :disabled="!canMove(data, -1)" @click.stop="moveNode(data, -1)">上移</el-button>
            <el-button v-if="user.hasPerm('fault:edit')" size="small" link
              :disabled="!canMove(data, 1)" @click.stop="moveNode(data, 1)">下移</el-button>
            <el-button v-if="user.hasPerm('fault:edit') && data.level < 3" size="small" link type="primary"
              @click.stop="openCreate(data.id)">添加子级</el-button>
            <el-button v-if="user.hasPerm('fault:edit')" size="small" link type="primary"
              @click.stop="openEdit(data)">编辑</el-button>
            <el-button v-if="user.hasPerm('fault:edit')" size="small" link type="danger"
              @click.stop="onDelete(data)">删除</el-button>
          </span>
        </div>
      </template>
    </el-tree>
    <el-empty v-if="!loading && !tree.length" description="暂无分类" :image-size="50" />

    <el-dialog v-model="formVisible" :title="form.id ? '编辑分类' : '新增分类'" width="420px" destroy-on-close>
      <el-form ref="formRef" :model="form" label-width="80px">
        <el-form-item v-if="form.parent_id" label="上级分类">
          <el-tag size="small">{{ parentName }}</el-tag>
        </el-form-item>
        <el-form-item v-else label="层级">
          <el-tag size="small" type="primary">一级</el-tag>
        </el-form-item>
        <el-form-item label="名称" prop="name"
          :rules="[{ required: true, message: '请输入分类名称', trigger: 'blur' }]">
          <el-input v-model="form.name" placeholder="分类名称" />
        </el-form-item>
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
import { ref, reactive, computed, onMounted } from 'vue'
import { Plus } from '@element-plus/icons-vue'
import {
  fetchFaultCategories, createFaultCategory, updateFaultCategory, deleteFaultCategory,
  reorderFaultCategories,
  type FaultCategoryNode,
} from '@/api/faults'
import { useUserStore } from '@/stores/user'
import { useUiStore } from '@/stores/ui'

const emit = defineEmits<{ (e: 'changed'): void }>()
const user = useUserStore()
const ui = useUiStore()

const tree = ref<FaultCategoryNode[]>([])
const loading = ref(false)
const formVisible = ref(false)
const saving = ref(false)
const formRef = ref()
const form = reactive<Record<string, unknown>>({ id: null, name: '', parent_id: null })

const parentName = computed(() => {
  const p = findNode(tree.value, Number(form.parent_id))
  return p?.name || ''
})

function findNode(nodes: FaultCategoryNode[], id: number): FaultCategoryNode | undefined {
  for (const n of nodes) {
    if (n.id === id) return n
    const hit = findNode(n.children || [], id)
    if (hit) return hit
  }
  return undefined
}

function levelTag(level: number): 'primary' | 'success' | 'warning' | 'info' {
  return (['', 'primary', 'success', 'warning'] as const)[level] || 'info'
}

function load() {
  loading.value = true
  fetchFaultCategories()
    .then((d) => { tree.value = d })
    .catch(() => { /* toast */ })
    .finally(() => { loading.value = false })
}

function openCreate(parentId?: number | null) {
  Object.assign(form, { id: null, name: '', parent_id: parentId ?? null })
  formVisible.value = true
}

function openEdit(node: FaultCategoryNode) {
  Object.assign(form, { id: node.id, name: node.name, parent_id: node.parent_id })
  formVisible.value = true
}

async function save() {
  try { await formRef.value?.validate() } catch { return }
  saving.value = true
  try {
    const payload = { name: String(form.name) }
    if (form.id) {
      await updateFaultCategory(form.id as number, payload)
      ui.toast('已保存', 'success')
    } else {
      await createFaultCategory({
        name: String(form.name),
        parent_id: form.parent_id ? Number(form.parent_id) : null,
      })
      ui.toast('已添加', 'success')
    }
    formVisible.value = false
    load()
    emit('changed')
  } catch (e) {
    ui.toast((e as Error).message, 'error')
  } finally {
    saving.value = false
  }
}

function allowDrop(draggingNode: { data: FaultCategoryNode },
                   dropNode: { data: FaultCategoryNode }, type: string) {
  return type !== 'inner' && draggingNode.data.parent_id === dropNode.data.parent_id
}

async function onNodeDrop(draggingNode: { data: FaultCategoryNode }) {
  const parentId = draggingNode.data.parent_id
  const siblings = parentId == null ? tree.value : (findNode(tree.value, parentId)?.children || [])
  try {
    await reorderFaultCategories(parentId, siblings.map((item) => item.id))
    ui.toast('排序已保存', 'success')
    emit('changed')
  } catch (e) {
    ui.toast((e as Error).message, 'error')
    load()
  }
}

function siblingList(node: FaultCategoryNode) {
  return node.parent_id == null ? tree.value : (findNode(tree.value, node.parent_id)?.children || [])
}

function canMove(node: FaultCategoryNode, delta: number) {
  const siblings = siblingList(node)
  const index = siblings.findIndex((item) => item.id === node.id)
  return index >= 0 && index + delta >= 0 && index + delta < siblings.length
}

async function moveNode(node: FaultCategoryNode, delta: number) {
  const siblings = siblingList(node)
  const index = siblings.findIndex((item) => item.id === node.id)
  const target = index + delta
  if (index < 0 || target < 0 || target >= siblings.length) return
  const next = [...siblings]
  ;[next[index], next[target]] = [next[target], next[index]]
  try {
    await reorderFaultCategories(node.parent_id, next.map((item) => item.id))
    ui.toast('排序已保存', 'success')
    load()
    emit('changed')
  } catch (e) {
    ui.toast((e as Error).message, 'error')
  }
}

async function onDelete(node: FaultCategoryNode) {
  try {
    await ElMessageBox.confirm(`确定删除「${node.name}」吗？`, '删除确认', { type: 'warning' })
  } catch { return }
  try {
    await deleteFaultCategory(node.id)
    ui.toast('已删除', 'success')
    load()
    emit('changed')
  } catch (e) {
    ui.toast((e as Error).message, 'error')
  }
}

onMounted(load)
</script>

<style scoped>
.cat-toolbar {
  display: flex;
  justify-content: flex-end;
  margin-bottom: 10px;
}
.cat-tree {
  max-height: 55vh;
  overflow: auto;
}
.cat-node {
  display: flex;
  align-items: center;
  gap: 8px;
  flex: 1;
  padding-right: 8px;
}
.cat-level {
  flex-shrink: 0;
}
.cat-name {
  flex: 1;
  font-size: 13px;
}
.cat-actions {
  display: inline-flex;
  gap: 2px;
}
</style>
