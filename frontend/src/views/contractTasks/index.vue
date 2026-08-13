<template>
  <div class="page-container">
    <div class="page-header">
      <h2 class="page-title">合同巡检配置</h2>
    </div>

    <el-card shadow="never">
      <div class="toolbar">
        <el-select v-model="selectedContract" placeholder="手动触发：选择合同" filterable clearable style="width: 280px">
          <el-option
            v-for="c in data?.all_contracts || []"
            :key="c.id"
            :label="`${c.title}（${c.customer_name}）`"
            :value="c.id"
          />
        </el-select>
        <el-date-picker
          v-model="toDate"
          type="date"
          placeholder="生成至（默认今天）"
          value-format="YYYY-MM-DD"
          style="width: 180px"
        />
        <el-button type="primary" :disabled="!selectedContract" :loading="generating" @click="onGenerate()">
          生成巡检任务
        </el-button>
      </div>
    </el-card>

    <el-card shadow="never" class="mt-3">
      <el-table v-loading="loading" :data="data?.contracts || []" border row-key="id" size="default">
        <el-table-column prop="title" :label="label('contract', 'title', '合同标题')" min-width="220" />
        <el-table-column prop="customer_name" :label="label('contract', 'customer_name', '客户')" min-width="120" />
        <el-table-column prop="inspection_frequency" :label="label('contract', 'inspection_frequency', '巡检频率')" width="100">
          <template #default="{ row }">
            <el-tag size="small" type="warning">{{ row.inspection_frequency }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="auto_generate_tasks" :label="label('contract', 'auto_generate_tasks', '自动巡检')" width="90">
          <template #default="{ row }">
            <el-tag size="small" :type="row.auto_generate_tasks ? 'success' : 'info'">
              {{ row.auto_generate_tasks ? '开启' : '关闭' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="end_date" :label="label('contract', 'end_date', '结束日期')" width="110">
          <template #default="{ row }">{{ row.end_date || '-' }}</template>
        </el-table-column>
        <el-table-column label="操作" width="200" fixed="right">
          <template #default="{ row }">
            <el-button size="small" link type="primary" @click="onPreview(row)">预览</el-button>
            <el-button size="small" link type="primary" @click="onShowTasks(row)">已生成任务</el-button>
            <el-button size="small" link type="primary" :loading="genSet.has(row.id)" @click="onGenerate(row)">生成</el-button>
          </template>
        </el-table-column>
      </el-table>
      <el-empty v-if="!loading && !data?.contracts?.length" description="暂无已配置巡检频率的合同" :image-size="60" />
    </el-card>

    <!-- 预览弹窗 -->
    <el-dialog v-model="previewVisible" title="预览将生成的任务" width="640px">
      <div v-if="previewMsg" class="preview-msg">{{ previewMsg }}</div>
      <el-table v-if="previewTasks.length" :data="previewTasks" size="small" border max-height="420">
        <el-table-column prop="title" :label="label('contract_inspection_task', 'title', '任务标题')" min-width="200" />
        <el-table-column prop="planned_start" :label="label('contract_inspection_task', 'planned_start', '计划开始')" width="110" />
        <el-table-column prop="planned_end" :label="label('contract_inspection_task', 'planned_end', '计划结束')" width="110" />
        <el-table-column prop="assigned_to" :label="label('contract_inspection_task', 'assigned_to', '负责人')" width="100">
          <template #default="{ row }">{{ row.assigned_to_name || row.assigned_to || '-' }}</template>
        </el-table-column>
      </el-table>
    </el-dialog>

    <!-- 已生成任务弹窗 -->
    <el-dialog v-model="tasksVisible" title="已生成的巡检任务" width="640px">
      <el-table v-if="generatedTasks.length" :data="generatedTasks" size="small" border max-height="420">
        <el-table-column prop="title" :label="label('contract_inspection_task', 'title', '任务标题')" min-width="220" />
        <el-table-column prop="status" :label="label('contract_inspection_task', 'status', '状态')" width="100">
          <template #default="{ row }">
            <el-tag size="small">{{ row.status }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="planned_start" :label="label('contract_inspection_task', 'planned_start', '计划开始')" width="110" />
        <el-table-column prop="planned_end" :label="label('contract_inspection_task', 'planned_end', '计划结束')" width="110" />
      </el-table>
      <el-empty v-else description="暂无生成记录" :image-size="50" />
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, reactive } from 'vue'
import {
  fetchContractTasks, generateContractTasks, previewContractTasks, fetchGeneratedTasks,
  type ContractTaskListData, type ContractTaskItem,
} from '@/api/contractTasks'
import { useUiStore } from '@/stores/ui'
import { entityFieldLabel, fetchEntityMetas, type EntityMeta } from '@/api/meta'

const ui = useUiStore()
const data = ref<ContractTaskListData | null>(null)
const loading = ref(false)
const generating = ref(false)
const genSet = ref(new Set<number>())
const genSetMut = {
  add: (id: number) => { genSet.value = new Set(genSet.value).add(id) },
  delete: (id: number) => { const s = new Set(genSet.value); s.delete(id); genSet.value = s },
}
const selectedContract = ref<number | null>(null)
const toDate = ref('')

const previewVisible = ref(false)
const previewTasks = ref<Array<Record<string, unknown>>>([])
const previewMsg = ref('')
const tasksVisible = ref(false)
const generatedTasks = ref<Array<Record<string, unknown>>>([])
const metadata = reactive<Record<string, EntityMeta>>({})
const label = (entity: string, key: string, fallback: string) =>
  entityFieldLabel(metadata[entity], key, fallback)

function load() {
  loading.value = true
  fetchContractTasks()
    .then((d) => { data.value = d })
    .catch(() => { /* toast */ })
    .finally(() => { loading.value = false })
}

async function onGenerate(row?: ContractTaskItem) {
  const id = row?.id ?? selectedContract.value
  if (!id) return
  genSetMut.add(id)
  generating.value = true
  try {
    const r = await generateContractTasks(id, toDate.value || undefined)
    ui.toast(`已生成 ${r.count} 个巡检任务`, 'success')
    selectedContract.value = null
  } catch (e) {
    ui.toast((e as Error).message, 'error')
  } finally {
    genSetMut.delete(id)
    generating.value = false
  }
}

async function onPreview(row: ContractTaskItem) {
  try {
    const r = await previewContractTasks(row.id)
    previewTasks.value = (r.tasks as Array<Record<string, unknown>>) || []
    previewMsg.value = ''
    previewVisible.value = true
  } catch (e) {
    previewMsg.value = (e as Error).message
    previewTasks.value = []
    previewVisible.value = true
  }
}

async function onShowTasks(row: ContractTaskItem) {
  try {
    generatedTasks.value = (await fetchGeneratedTasks(row.id)) as unknown as Array<Record<string, unknown>>
    tasksVisible.value = true
  } catch { /* toast */ }
}

onMounted(() => {
  load()
  fetchEntityMetas(['contract', 'contract_inspection_task'])
    .then((metas) => Object.assign(metadata, metas))
})
</script>

<style scoped>
.toolbar {
  display: flex;
  gap: 8px;
  align-items: center;
  flex-wrap: wrap;
}
.mt-3 {
  margin-top: 12px;
}
.preview-msg {
  color: var(--itsm-text-muted);
  margin-bottom: 8px;
}
</style>
