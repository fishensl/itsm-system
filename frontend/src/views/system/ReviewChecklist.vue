<template>
  <div class="page-container">
    <div class="page-header">
      <h2 class="page-title">巡检审核清单</h2>
      <div class="header-actions">
        <el-button :icon="Plus" plain @click="addItem">添加检查项</el-button>
        <el-button type="primary" :icon="Check" :loading="saving" @click="save">保存</el-button>
      </div>
    </div>

    <el-card shadow="never">
      <div class="tips">
        审核人打开巡检审核弹窗时逐项核对（合格 / 需修改 / 不适用），勾选结果随每轮审核留痕；
        退回时「需修改」项自动生成修改要求，工程师据此修改重传。
      </div>
      <el-table :data="items" size="small" border stripe>
        <el-table-column :label="label('sort_order', '顺序')" width="70" align="center">
          <template #default="{ $index }">{{ $index + 1 }}</template>
        </el-table-column>
        <el-table-column :label="label('name', '检查项名称')" min-width="220">
          <template #default="{ row }">
            <el-input v-model="row.name" size="small" placeholder="如：核心设备配置备份" />
          </template>
        </el-table-column>
        <el-table-column :label="label('enabled', '启用')" width="90" align="center">
          <template #default="{ row }">
            <el-switch v-model="row.enabled" />
          </template>
        </el-table-column>
        <el-table-column label="操作" width="160" align="center">
          <template #default="{ $index }">
            <el-button size="small" link :disabled="$index === 0" :icon="ArrowUp" @click="move($index, -1)" />
            <el-button size="small" link :disabled="$index === items.length - 1" :icon="ArrowDown"
              @click="move($index, 1)" />
            <el-button size="small" link type="danger" :icon="Delete" @click="removeItem($index)" />
          </template>
        </el-table-column>
      </el-table>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { Plus, Check, Delete, ArrowUp, ArrowDown } from '@element-plus/icons-vue'
import { useUiStore } from '@/stores/ui'
import { fetchReviewChecklist, updateReviewChecklist, type ReviewChecklistItem } from '@/api/inspections'
import { entityFieldLabel, fetchEntityMeta, type EntityMeta } from '@/api/meta'

const ui = useUiStore()
const items = ref<ReviewChecklistItem[]>([])
const metadata = ref<EntityMeta>()
const saving = ref(false)

function label(key: string, fallback: string) {
  return entityFieldLabel(metadata.value, key, fallback, 'list')
}

function addItem() {
  items.value.push({ name: '', enabled: true })
}

function removeItem(i: number) {
  items.value.splice(i, 1)
}

function move(i: number, dir: number) {
  const j = i + dir
  if (j < 0 || j >= items.value.length) return
  const tmp = items.value[i]
  items.value[i] = items.value[j]
  items.value[j] = tmp
}

async function save() {
  const cleaned = items.value
    .map((it) => ({ name: (it.name || '').trim(), enabled: it.enabled }))
    .filter((it) => it.name)
  if (!cleaned.length) {
    ui.toast('至少保留一个检查项', 'warning')
    return
  }
  saving.value = true
  try {
    await updateReviewChecklist(cleaned)
    items.value = cleaned
    ui.toast('已保存', 'success')
  } catch (e) {
    ui.toast((e as Error).message, 'error')
  } finally {
    saving.value = false
  }
}

onMounted(() => {
  fetchReviewChecklist()
    .then((r) => { items.value = r.items })
    .catch(() => { /* toast */ })
  fetchEntityMeta('review_checklist')
    .then((result) => { metadata.value = result })
    .catch(() => { /* 兼容滚动发布期间的旧后端 */ })
})
</script>

<style scoped>
.page-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; }
.header-actions { display: flex; gap: 8px; }
.tips {
  font-size: 12px; color: var(--itsm-text-muted); background: var(--el-color-primary-light-9);
  border: 1px solid var(--el-color-primary-light-5); border-radius: 6px; padding: 8px 12px; margin-bottom: 12px;
}
</style>
