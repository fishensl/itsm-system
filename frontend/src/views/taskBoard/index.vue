<template>
  <div class="page-container">
    <div class="page-header">
      <h2 class="page-title">任务看板</h2>
      <div class="header-actions">
        <el-button size="small" :icon="Refresh" @click="reload">刷新</el-button>
      </div>
    </div>

    <!-- 筛选 -->
    <el-card shadow="never" class="filter-card">
      <div class="filter-row">
        <el-select v-model="query.customer_id" placeholder="客户" clearable filterable class="filter-item"
          @change="reload">
          <el-option v-for="c in dicts?.customers || []" :key="c.id" :label="c.name" :value="c.id" />
        </el-select>
        <el-select v-model="query.assignee_id" placeholder="负责人" clearable class="filter-item"
          @change="reload">
          <el-option v-for="a in dicts?.assignees || []" :key="a.id" :label="a.name" :value="a.id" />
        </el-select>
        <el-checkbox v-model="showCancelled" @change="reload">含已取消</el-checkbox>
        <span class="board-summary">
          待执行 <b>{{ board?.pending ?? 0 }}</b> · 执行中 <b>{{ board?.running ?? 0 }}</b> ·
          已完成 <b>{{ board?.done ?? 0 }}</b>
        </span>
      </div>
    </el-card>

    <!-- 看板 -->
    <div v-loading="loading" class="board">
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
                v-if="t.status === '待执行' && user.hasPerm('task:dispatch')" size="small"
                type="warning" plain @click="changeStatus(t, '执行中')">开始</el-button>
              <el-button
                v-if="t.status === '执行中' && user.hasPerm('task:dispatch')" size="small"
                type="success" plain @click="changeStatus(t, '已完成')">完成</el-button>
              <el-button
                v-if="t.status === '待执行' && user.hasPerm('task:dispatch')" size="small"
                type="info" plain @click="changeStatus(t, '已取消')">取消</el-button>
            </div>
          </div>
          <el-empty v-if="!board?.groups?.[st]?.length" description="暂无任务" :image-size="40" />
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted } from 'vue'
import { Refresh } from '@element-plus/icons-vue'
import { useUserStore } from '@/stores/user'
import { useUiStore } from '@/stores/ui'
import {
  fetchTaskBoard, setTaskStatus, fetchTaskBoardDicts, type TaskBoard, type TaskBoardDicts,
} from '@/api/taskBoard'

const user = useUserStore()
const ui = useUiStore()
const board = ref<TaskBoard | null>(null)
const dicts = ref<TaskBoardDicts | null>(null)
const loading = ref(false)
const showCancelled = ref(false)

const query = reactive<Record<string, unknown>>({ customer_id: undefined, assignee_id: undefined })
const statusOrder = ['待执行', '执行中', '已完成']

function statusClass(st: string) {
  return { 待执行: 'pending', 执行中: 'running', 已完成: 'done' }[st] || ''
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
  try {
    await setTaskStatus(t.id, status)
    ui.toast(`「${t.title}」已改为 ${status}`, 'success')
    reload()
  } catch (e) {
    ui.toast((e as Error).message, 'error')
  }
}

onMounted(() => {
  reload()
  fetchTaskBoardDicts().then((d) => (dicts.value = d))
})
</script>

<style scoped>
.filter-card { margin-bottom: 12px; }
.filter-row { display: flex; gap: 8px; flex-wrap: wrap; align-items: center; }
.filter-item { width: 160px; max-width: 100%; }
.board-summary { margin-left: auto; font-size: 12px; color: var(--itsm-text-muted); }
.board { display: flex; gap: 12px; align-items: flex-start; overflow-x: auto; padding-bottom: 8px; }
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
.col-done { background: #67c23a22; color: #67c23a; }
.col-count { font-weight: 400; font-size: 12px; }
.board-col-body {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 8px;
  max-height: calc(100vh - 240px);
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
