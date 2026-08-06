<template>
  <div class="data-table">
    <!-- 桌面/平板：表格 -->
    <div v-if="!isMobile" class="table-wrap">
      <el-table
        v-loading="loading"
        :data="items"
        border
        stripe
        size="small"
        :max-height="maxHeight"
        @row-click="onRowClick"
      >
        <el-table-column
          v-for="col in columns"
          :key="col.key"
          :label="col.label"
          :width="col.width"
          :min-width="col.minWidth"
          :fixed="col.fixed"
          :align="col.align || 'left'"
          :show-overflow-tooltip="col.ellipsis !== false"
        >
          <template #default="{ row }">
            <!-- 状态徽章 -->
            <el-tag v-if="col.type === 'tag'" size="small" :type="tagType(row, col)">
              {{ displayValue(row, col) ?? '-' }}
            </el-tag>
            <!-- 链接 -->
            <router-link v-else-if="col.type === 'link'" :to="toRouterPath(col.link?.(row) ?? '#')" class="row-link">
              {{ displayValue(row, col) ?? '-' }}
            </router-link>
            <!-- 自定义渲染（render 返回字符串或 VNode） -->
            <CustomCell v-else-if="col.type === 'custom'" :render="() => col.render?.(row)" />
            <!-- 操作按钮组 -->
            <div v-else-if="col.type === 'action'" class="row-actions" @click.stop>
              <el-button
                v-for="act in visibleActions(row, col)"
                :key="act.label"
                size="small"
                :type="act.type || 'primary'"
                :plain="act.plain"
                :link="act.link"
                :disabled="act.disabled?.(row)"
                @click="act.onClick(row)"
              >
                <el-icon v-if="act.icon"><component :is="act.icon" /></el-icon>
                <span v-if="act.label">{{ act.label }}</span>
              </el-button>
            </div>
            <!-- 金额 -->
            <span v-else-if="col.type === 'money'">{{ fmtMoney(row[col.key]) }}</span>
            <!-- 日期 -->
            <span v-else-if="col.type === 'date'">{{ displayValue(row, col) ?? '-' }}</span>
            <!-- 文本（支持高亮） -->
            <span v-else :class="col.cellClass?.(row)">{{ displayValue(row, col) ?? '-' }}</span>
          </template>
        </el-table-column>
        <template #empty>
          <el-empty :description="emptyText" :image-size="60" />
        </template>
      </el-table>

      <!-- 分页 -->
      <div v-if="total > 0" class="table-pagination">
        <el-pagination
          v-model:current-page="page"
          v-model:page-size="pageSize"
          :total="total"
          :page-sizes="[10, 20, 50, 100]"
          layout="total, sizes, prev, pager, next, jumper"
          small
          background
          @change="load"
        />
      </div>
    </div>

    <!-- 移动端：卡片列表 -->
    <div v-else>
      <div v-loading="loading" class="card-list">
        <div v-for="row in items" :key="row[rowKey]" class="mobile-card" @click="onRowClick(row)">
          <div class="card-main">
            <div class="card-title-row">
              <span v-if="titleCol" class="card-title">{{ row[titleCol.key] ?? '-' }}</span>
              <el-tag
                v-if="tagCol"
                size="small"
                :type="tagType(row, tagCol)"
                class="card-tag"
              >
                {{ displayValue(row, tagCol) ?? '-' }}
              </el-tag>
            </div>
            <div class="card-fields">
              <span v-for="col in bodyCols" :key="col.key" class="card-field">
                <span class="card-field-label">{{ col.label }}：</span>
                <span class="card-field-value">
                  <CustomCell v-if="col.type === 'custom'" :render="() => col.render?.(row)" />
                  <template v-else>{{ displayValue(row, col) ?? '-' }}</template>
                </span>
              </span>
            </div>
          </div>
          <div v-if="actionCol && visibleActions(row, actionCol).length" class="card-actions" @click.stop>
            <el-button
              v-for="act in visibleActions(row, actionCol)"
              :key="act.label"
              size="small"
              :type="act.type || 'primary'"
              :plain="act.plain"
              :disabled="act.disabled?.(row)"
              @click="act.onClick(row)"
            >
              <el-icon v-if="act.icon"><component :is="act.icon" /></el-icon>
              <span v-if="act.label">{{ act.label }}</span>
            </el-button>
          </div>
        </div>
        <el-empty v-if="!loading && items.length === 0" :description="emptyText" :image-size="60" />
      </div>

      <!-- 分页 -->
      <div v-if="total > 0" class="table-pagination">
        <el-pagination
          v-model:current-page="page"
          v-model:page-size="pageSize"
          :total="total"
          layout="prev, pager, next"
          small
          background
          @change="load"
        />
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, onMounted, onBeforeUnmount, defineComponent, type VNode } from 'vue'
import type { PageResult } from '@/types'
import { toRouterPath } from '@/utils/sidebarNav'

/** 自定义单元格渲染（type='custom'）：render 返回字符串或 VNode */
const CustomCell = defineComponent({
  props: { render: { type: Function, default: null } },
  setup(props) {
    return () => {
      const r = (props as { render?: () => string | VNode | undefined }).render
      return r ? r() : null
    }
  },
})

export interface DataAction<T = Record<string, any>> {
  label?: string
  icon?: string
  type?: 'primary' | 'success' | 'warning' | 'danger' | 'info'
  plain?: boolean
  link?: boolean
  perm?: string
  disabled?: (row: T) => boolean
  onClick: (row: T) => void
}

export interface DataColumn<T = Record<string, any>> {
  key: string
  label: string
  type?: 'text' | 'tag' | 'link' | 'action' | 'money' | 'date' | 'custom'
  width?: number
  minWidth?: number
  fixed?: boolean | 'left' | 'right'
  align?: 'left' | 'center' | 'right'
  ellipsis?: boolean
  /** type='custom'：自定义单元格渲染（返回字符串或 VNode），桌面表格与移动端卡片通用 */
  render?: (row: T) => string | VNode | undefined
  /** tag 类型的颜色映射：值 → el-tag type */
  tagMap?: Record<string, 'primary' | 'success' | 'warning' | 'danger' | 'info'>
  /** 显示文本映射：值 → 中文文本（布尔/枚举英文值显示层翻译，tag/text/link 列通用） */
  valueMap?: Record<string, string>
  link?: (row: T) => string
  cellClass?: (row: T) => string
  actions?: DataAction<T>[]
  /** 移动端卡片：作为标题列 / 徽章列 */
  asTitle?: boolean
  asTag?: boolean
}

const props = withDefaults(
  defineProps<{
    columns: DataColumn[]
    /** 数据加载函数：返回分页结果 */
    fetchData: (params: Record<string, any>) => Promise<PageResult<Record<string, any>>>
    /** 初始筛选条件（变化时自动重新加载） */
    query?: Record<string, unknown>
    rowKey?: string
    emptyText?: string
    maxHeight?: number | string
    immediate?: boolean
  }>(),
  {
    rowKey: 'id',
    emptyText: '暂无数据',
    immediate: true,
  },
)

const emit = defineEmits<{ (e: 'row-click', row: Record<string, any>): void }>()

const items = ref<Record<string, any>[]>([])
const total = ref(0)
const page = ref(1)
const pageSize = ref(20)
const loading = ref(false)
const isMobile = ref(false)

// 筛选变化防抖：文本输入击键不立即发请求，避免每敲一键一次 API 调用
let queryTimer: ReturnType<typeof setTimeout> | null = null

const titleCol = computed(() => props.columns.find((c) => c.asTitle))
const tagCol = computed(() => props.columns.find((c) => c.asTag))
const actionCol = computed(() => props.columns.find((c) => c.type === 'action'))
const bodyCols = computed(() =>
  props.columns.filter((c) => c.type !== 'action' && c !== titleCol.value && c !== tagCol.value),
)

function tagType(row: Record<string, any>, col: DataColumn) {
  const v = row[col.key]
  if (v === null || v === undefined) return 'info'
  return col.tagMap?.[String(v)] ?? 'info'
}

/** 单元格显示文本：valueMap 翻译（布尔/数字先 String 化），无映射回退原值 */
function displayValue(row: Record<string, any>, col: DataColumn) {
  const v = row[col.key]
  if (v === null || v === undefined) return undefined
  const mapped = col.valueMap?.[String(v)]
  if (mapped !== undefined) return mapped
  return typeof v === 'string' ? v : String(v)
}

function visibleActions(row: Record<string, any>, col: DataColumn) {
  return (col.actions || []).filter((a) => {
    if (a.perm && !hasPerm(a.perm)) return false
    return !a.disabled?.(row)
  })
}

function fmtMoney(v: unknown) {
  const n = Number(v ?? 0)
  return n.toLocaleString('zh-CN', { minimumFractionDigits: 0, maximumFractionDigits: 2 })
}

async function load() {
  loading.value = true
  try {
    const params: Record<string, unknown> = { page: page.value, page_size: pageSize.value, ...props.query }
    const result = await props.fetchData(params)
    items.value = result.items
    total.value = result.total
    // 页码越界回退
    if (result.total > 0 && result.items.length === 0 && page.value > 1) {
      page.value = Math.max(1, Math.ceil(result.total / pageSize.value))
      return load()
    }
  } catch {
    /* 拦截器已提示 */
  } finally {
    loading.value = false
  }
}

function onRowClick(row: Record<string, unknown>) {
  emit('row-click', row)
}

function refresh() {
  page.value = 1
  load()
}

watch(
  () => props.query,
  () => {
    if (queryTimer) clearTimeout(queryTimer)
    queryTimer = setTimeout(() => refresh(), 250)
  },
  { deep: true },
)

const mq = window.matchMedia('(max-width: 767px)')
function onMq(e: MediaQueryListEvent | MediaQueryList) {
  isMobile.value = e.matches
}

onMounted(() => {
  onMq(mq)
  mq.addEventListener('change', onMq)
  if (props.immediate) load()
})

onBeforeUnmount(() => {
  mq.removeEventListener('change', onMq)
  if (queryTimer) clearTimeout(queryTimer)
})

defineExpose({ refresh, load })

// 权限判定（避免循环依赖：从全局 store 读取）
import { useUserStore } from '@/stores/user'
const hasPerm = (code?: string) => useUserStore().hasPerm(code)
</script>

<style scoped>
.table-wrap {
  overflow-x: auto;
}
.table-pagination {
  display: flex;
  justify-content: flex-end;
  padding: 10px 0 0;
  flex-wrap: wrap;
  gap: 8px;
}
.row-link {
  color: var(--el-color-primary);
  text-decoration: none;
  font-weight: 500;
}
.row-actions {
  display: flex;
  gap: 4px;
  flex-wrap: nowrap;
  white-space: nowrap;
}

/* 移动端卡片 */
.card-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.mobile-card {
  background: var(--itsm-card-bg);
  border: 1px solid var(--itsm-border);
  border-radius: 10px;
  padding: 12px;
  cursor: pointer;
}
.mobile-card:active {
  background: var(--el-fill-color-light);
}
.card-title-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  margin-bottom: 8px;
}
.card-title {
  font-weight: 600;
  font-size: 14px;
  color: var(--el-color-primary);
}
.card-tag {
  flex-shrink: 0;
}
.card-fields {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.card-field {
  font-size: 12px;
  display: flex;
  justify-content: space-between;
  gap: 8px;
}
.card-field-label {
  color: var(--itsm-text-muted);
  flex-shrink: 0;
}
.card-field-value {
  text-align: right;
  word-break: break-all;
}
.card-actions {
  display: flex;
  gap: 6px;
  margin-top: 10px;
  padding-top: 10px;
  border-top: 1px dashed var(--itsm-border);
  flex-wrap: wrap;
}
</style>
