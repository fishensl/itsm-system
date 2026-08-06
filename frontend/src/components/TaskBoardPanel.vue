<template>
  <div class="task-board-panel">
    <!-- 筛选（compact 模式下默认隐藏，可用 showFilters 显式开启） -->
    <div v-if="showFilters" class="filter-row">
      <el-select v-model="query.customer_id" placeholder="客户" clearable filterable class="filter-item"
        @change="reload">
        <el-option v-for="c in dicts?.customers || []" :key="c.id" :label="c.name" :value="c.id" />
      </el-select>
      <el-select v-model="query.assignee_id" placeholder="负责人" clearable class="filter-item"
        @change="reload">
        <el-option v-for="a in dicts?.assignees || []" :key="a.id" :label="a.name" :value="a.id" />
      </el-select>
      <el-checkbox v-model="showCancelled" @change="reload">含已取消</el-checkbox>
      <span v-if="board?.scope" class="scope-tag">
        <el-tag size="small" :type="scopeTagType" effect="plain">{{ board.scope_label }}</el-tag>
      </span>
      <span class="board-summary">
        待执行 <b>{{ board?.pending ?? 0 }}</b> · 执行中 <b>{{ board?.running ?? 0 }}</b> ·
        已完成 <b>{{ board?.done ?? 0 }}</b>
      </span>
      <el-button size="small" :icon="Refresh" circle plain @click="reload" />
    </div>

    <!-- 看板 -->
    <div v-loading="loading" class="board" :class="{ 'board-compact': compact }">
      <div v-for="st in statusOrder" :key="st" class="board-col">
        <div class="board-col-header" :class="`col-${statusClass(st)}`">
          <span>{{ st }}</span>
          <span class="col-count">{{ board?.groups?.[st]?.length ?? 0 }}</span>
        </div>
        <div class="board-col-body">
          <div v-for="t in board?.groups?.[st] || []" :key="t.id" class="board-card">
            <div class="card-top">
              <span class="card-title">{{ t.title }}</span>
              <el-tag v-if="t.overdue" size="small" type="danger">逾期</el-tag>
            </div>
            <div class="card-meta">
              <span>{{ t.customer_name || '未关联客户' }}</span>
              <span v-if="t.planned_start || t.planned_end" class="card-date">
                {{ t.planned_start }} ~ {{ t.planned_end }}
              </span>
            </div>
            <div class="card-meta">
              <span>{{ t.assigned_to_name || '未指派' }}</span>
              <span v-if="t.estimated_effort" class="card-date">预估 {{ t.estimated_effort }} 人天</span>
            </div>
            <div class="card-actions">
              <el-button
                v-if="t.status === TASK_STATUS.PENDING && user.hasPerm('task:dispatch')" size="small"
                type="warning" plain @click="changeStatus(t, TASK_STATUS.RUNNING)">开始</el-button>
              <el-button
                v-if="t.status === TASK_STATUS.RUNNING && user.hasPerm('task:dispatch')" size="small"
                type="success" plain @click="changeStatus(t, TASK_STATUS.DONE)">完成</el-button>
              <el-button
                v-if="t.status === TASK_STATUS.PENDING && user.hasPerm('task:dispatch')" size="small"
                type="info" plain @click="changeStatus(t, TASK_STATUS.CANCELLED)">取消</el-button>
              <el-button
                v-if="t.status === TASK_STATUS.REVIEWING && user.hasPerm('task:dispatch')" size="small"
                type="warning" plain @click="changeStatus(t, TASK_STATUS.RUNNING)">退回执行</el-button>
            </div>
          </div>
          <el-empty v-if="!board?.groups?.[st]?.length" description="暂无任务" :image-size="40" />
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ElMessageBox } from 'element-plus/es/components/message-box/index'
import { ref, reactive, computed, onMounted } from 'vue'
import { Refresh } from '@element-plus/icons-vue'
import { useUserStore } from '@/stores/user'
import { useUiStore } from '@/stores/ui'
import { TASK_STATUS } from '@/utils/status'
import {
  fetchTaskBoard, setTaskStatus, fetchTaskBoardDicts, type TaskBoard, type TaskBoardDicts,
} from '@/api/taskBoard'

const props = withDefaults(defineProps<{
  compact?: boolean
  showFilters?: boolean
}>(), {
  compact: false,
  showFilters: true,
})

const user = useUserStore()
const ui = useUiStore()
const board = ref<TaskBoard | null>(null)
const dicts = ref<TaskBoardDicts | null>(null)
const loading = ref(false)
const showCancelled = ref(false)

const query = reactive<Record<string, unknown>>({ customer_id: undefined, assignee_id: undefined })
const statusOrder = [TASK_STATUS.PENDING, TASK_STATUS.RUNNING, TASK_STATUS.REVIEWING, TASK_STATUS.DONE]

const scopeTagType = computed(() => ({
  all: 'success',
  dept: 'primary',
  mine: 'warning',
})[board.value?.scope || 'all'] as 'success' | 'primary' | 'warning')

function statusClass(st: string) {
  return {
    [TASK_STATUS.PENDING]: 'pending',
    [TASK_STATUS.RUNNING]: 'running',
    [TASK_STATUS.REVIEWING]: 'reviewing',
    [TASK_STATUS.DONE]: 'done',
  }[st] || ''
}

async function reload() {
  loading.value = true
  try {
    board.value = await fetchTaskBoard({
      ...(query as object),
      show_cancelled: showCancelled.value,
    })
  } catch {
    /* toast */
  } finally {
    loading.value = false
  }
}

async function changeStatus(t: { id: number; title: string }, status: string) {
  if (status === TASK_STATUS.CANCELLED) {
    try {
      await ElMessageBox.confirm(`确定取消任务「${t.title}」吗？`, '取消确认', { type: 'warning' })
    } catch { return }
  }
  try {
    await setTaskStatus(t.id, status)
    ui.toast(`「${t.title}」已改为 ${status}`, 'success')
    reload()
  } catch (e) {
    ui.toast((e as Error).message, 'error')
  }
}

defineExpose({ reload })

onMounted(() => {
  reload()
  fetchTaskBoardDicts().then((d) => (dicts.value = d))
})
</script>

<style scoped>
.filter-row { display: flex; gap: 8px; flex-wrap: wrap; align-items: center; }
.filter-item { width: 160px; max-width: 100%; }
.scope-tag { flex-shrink: 0; }
.board-summary { margin-left: auto; font-size: 12px; color: var(--itsm-text-muted); }
.board { display: flex; gap: 12px; align-items: flex-start; overflow-x: auto; padding-bottom: 8px; }
.board-compact .board-col { min-width: 210px; }
.board-col {
  flex: 1;
  min-width: 260px;
  background: var(--itsm-card-bg);
  border: 1px solid var(--itsm-border);
  border-radius: 10px;
  overflow: hidden;
}
.board-col-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 12px;
  font-weight: 600;
  font-size: 13px;
}
.col-pending { background: #f56c6c22; color: #f56c6c; }
.col-running { background: #e6a23c22; color: #e6a23c; }
.col-reviewing { background: #409eff22; color: #409eff; }
.col-done { background: #67c23a22; color: #67c23a; }
.col-count { font-weight: 400; font-size: 12px; }
.board-col-body {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 8px;
  max-height: 420px;
  overflow-y: auto;
}
.board-card {
  border: 1px solid var(--itsm-border);
  border-radius: 8px;
  padding: 10px;
  background: var(--itsm-card-bg);
}
.card-top { display: flex; justify-content: space-between; gap: 6px; align-items: flex-start; }
.card-title { font-weight: 500; font-size: 13px; }
.card-meta { display: flex; justify-content: space-between; gap: 6px; font-size: 12px;
  color: var(--itsm-text-muted); margin-top: 4px; }
.card-date { flex-shrink: 0; }
.card-actions { display: flex; gap: 6px; margin-top: 8px; flex-wrap: wrap; }
</style>
