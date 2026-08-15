<template>
  <div class="page-container">
    <div class="page-header">
      <h2 class="page-title">合同巡检配置</h2>
    </div>

    <el-card shadow="never">
      <div class="toolbar">
        <el-select v-model="selectedContract" placeholder="手动触发：选择合同" filterable clearable style="width: 280px">
          <el-option
            v-for="c in allContracts"
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
      <DataTable
        :columns="columns"
        :fetch-data="fetchPage"
        row-key="id"
        empty-text="暂无已配置巡检频率的合同"
        :column-settings="{ storageKey: 'cols_contract_tasks' }"
      />
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
import { ref, onMounted, reactive, computed } from 'vue'
import {
  fetchContractTasks, generateContractTasks, previewContractTasks, fetchGeneratedTasks,
  type ContractTaskItem,
} from '@/api/contractTasks'
import { useUiStore } from '@/stores/ui'
import { entityFieldLabel, fetchEntityMetas, type EntityMeta } from '@/api/meta'
import DataTable, { type DataColumn } from '@/components/DataTable.vue'

const ui = useUiStore()
const allContracts = ref<Array<{
  id: number
  title: string
  customer_name: string
  inspection_frequency: string
}>>([])
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

const columns = computed<DataColumn[]>(() => {
  const result: DataColumn[] = [
  { key: 'title', label: label('contract_auto_contract', 'title', '合同标题'), minWidth: 220, asTitle: true },
  { key: 'customer_name', label: label('contract_auto_contract', 'customer_name', '客户'), minWidth: 120 },
  { key: 'inspection_frequency', label: label('contract_auto_contract', 'inspection_frequency', '巡检频率'),
    width: 100, type: 'tag', tagMap: {} },
  { key: 'auto_generate_tasks', label: label('contract_auto_contract', 'auto_generate_tasks', '自动巡检'),
    width: 90, type: 'tag', valueMap: { true: '开启', false: '关闭' },
    tagMap: { true: 'success', false: 'info' } },
  { key: 'end_date', label: label('contract_auto_contract', 'end_date', '结束日期'), width: 110, type: 'date' },
  { key: 'actions', label: '操作', width: 220, type: 'action', fixed: 'right', actions: [
    { label: '预览', type: 'primary', link: true,
      onClick: (row) => onPreview(row as unknown as ContractTaskItem) },
    { label: '已生成任务', type: 'primary', link: true,
      onClick: (row) => onShowTasks(row as unknown as ContractTaskItem) },
    { label: '生成', type: 'primary', link: true,
      disabled: (row) => genSet.value.has(Number(row.id)),
      loading: (row) => genSet.value.has(Number(row.id)),
      onClick: (row) => onGenerate(row as unknown as ContractTaskItem) },
  ] },
  ]
  return result
})

async function fetchPage(params: Record<string, unknown>) {
  const result = await fetchContractTasks()
  allContracts.value = result.all_contracts
  const page = Number(params.page) || 1
  const page_size = Number(params.page_size) || 20
  const start = (page - 1) * page_size
  return { items: result.contracts.slice(start, start + page_size), total: result.contracts.length,
    page, page_size }
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
  fetchEntityMetas(['contract_auto_contract', 'contract_inspection_task'])
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
