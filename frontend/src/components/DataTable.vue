<template>
  <div class="data-table">
    <!-- 桌面/平板：表格 -->
    <div v-if="!isMobile" class="table-wrap">
      <el-table
        ref="tableEl"
        v-loading="loading"
        :data="items"
        border
        stripe
        size="small"
        :max-height="maxHeight"
        @row-click="onRowClick"
      >
        <el-table-column v-if="expandable" type="expand" width="36">
          <template #default="scope">
            <slot name="expand" :row="scope.row" />
          </template>
        </el-table-column>
        <el-table-column
          v-for="col in renderCols"
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
          <div v-if="expandable && expandedKeys.has(String(row[rowKey]))" class="mobile-expand" @click.stop>
            <slot name="expand" :row="row" />
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

    <!-- 列设置弹窗 -->
    <el-dialog v-model="settingsVisible" :title="columnSettings?.title || '列设置'" width="420px" top="10vh"
      destroy-on-close>
      <div class="col-setting-list">
        <div v-for="(c, idx) in settingCols" :key="c.key" class="col-setting-row">
          <el-checkbox :model-value="c.visible" :disabled="isActionCol(c)"
            @change="(v: string | number | boolean) => toggleCol(c.key, Boolean(v))" />
          <span class="col-setting-name" :class="{ 'text-muted': !c.visible }">{{ c.label }}</span>
          <span class="col-setting-actions">
            <el-button size="small" text :icon="ArrowUp" :disabled="idx === 0" @click="moveCol(idx, -1)" />
            <el-button size="small" text :icon="ArrowDown" :disabled="idx === settingCols.length - 1"
              @click="moveCol(idx, 1)" />
          </span>
        </div>
        <el-empty v-if="!settingCols.length" description="无可配置列" :image-size="50" />
      </div>
      <template #footer>
        <el-button @click="resetColSettings">恢复默认</el-button>
        <el-button @click="settingsVisible = false">关闭</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, onMounted, onBeforeUnmount, defineComponent, type VNode } from 'vue'
import { Setting, ArrowUp, ArrowDown } from '@element-plus/icons-vue'
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
  /** 默认是否显示（默认 true）：仅未保存过列设置时生效；设为 false 的列默认隐藏，仍可去列设置开启 */
  defaultVisible?: boolean
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
    /** 行内展开详情：开启后点击行切换展开，内容渲染在 #expand 插槽 */
    expandable?: boolean
    /** 列设置（可选启用）：storageKey 为 localStorage 键；不传则无列设置功能 */
    columnSettings?: { storageKey: string; title?: string }
  }>(),
  {
    rowKey: 'id',
    emptyText: '暂无数据',
    immediate: true,
    expandable: false,
  },
)

const emit = defineEmits<{ (e: 'row-click', row: Record<string, any>): void }>()

const items = ref<Record<string, any>[]>([])
const total = ref(0)
const page = ref(1)
const pageSize = ref(20)
const loading = ref(false)
const isMobile = ref(false)
const tableEl = ref()
/** 移动端卡片展开的行 key 集合 */
const expandedKeys = ref<Set<string>>(new Set())

// ==================== 列设置（显示/隐藏 + 顺序，localStorage 持久化） ====================
const settingsVisible = ref(false)
/** 用户配置的可见列顺序（不含操作列，操作列强制显示在末尾） */
const colOrder = ref<string[] | null>(null)

function isActionCol(c: DataColumn) {
  return c.type === 'action'
}

function loadColSettings() {
  if (!props.columnSettings) return
  try {
    const raw = localStorage.getItem(props.columnSettings.storageKey)
    colOrder.value = raw ? JSON.parse(raw) : null
  } catch {
    colOrder.value = null
  }
}

function saveColSettings() {
  if (!props.columnSettings) return
  try {
    localStorage.setItem(props.columnSettings.storageKey, JSON.stringify(colOrder.value || []))
  } catch { /* localStorage 不可用时静默 */ }
}

/** 实际渲染列：用户顺序 + 可见性；未保存设置时按 defaultVisible 过滤；操作列固定末尾且不可隐藏 */
const renderCols = computed<DataColumn[]>(() => {
  const all = props.columns
  if (!props.columnSettings) return all
  const body = all.filter((c) => !isActionCol(c))
  const actions = all.filter((c) => isActionCol(c))
  if (!colOrder.value) {
    return [...body.filter((c) => c.defaultVisible !== false), ...actions]
  }
  const ordered: DataColumn[] = []
  for (const key of colOrder.value) {
    const hit = body.find((c) => c.key === key)
    if (hit && !ordered.includes(hit)) ordered.push(hit)
  }
  // 未显式勾选的默认隐藏列（defaultVisible:false）不追加回表格
  for (const c of body) {
    if (!ordered.includes(c) && c.defaultVisible !== false) ordered.push(c)
  }
  return [...ordered, ...actions]
})

const settingCols = computed(() => {
  const body = props.columns.filter((c) => !isActionCol(c))
  const order = colOrder.value || body.map((c) => c.key)
  const visible = (col: DataColumn) =>
    colOrder.value ? colOrder.value.includes(col.key) : col.defaultVisible !== false
  return order
    .map((key) => {
      const col = body.find((c) => c.key === key)
      return col ? { ...col, visible: visible(col) } : null
    })
    .filter((x): x is NonNullable<typeof x> => x !== null)
    .concat(body.filter((c) => !order.includes(c.key)).map((c) => ({ ...c, visible: false })))
})

function toggleCol(key: string, visible: boolean) {
  if (!colOrder.value) {
    colOrder.value = props.columns
      .filter((c) => !isActionCol(c) && c.defaultVisible !== false).map((c) => c.key)
  }
  const set = new Set(colOrder.value)
  if (visible) set.add(key)
  else set.delete(key)
  colOrder.value = props.columns.filter((c) => !isActionCol(c))
    .filter((c) => set.has(c.key)).map((c) => c.key)
  saveColSettings()
}

function moveCol(idx: number, dir: -1 | 1) {
  const arr = settingCols.value.map((c) => c.key)
  const j = idx + dir
  if (j < 0 || j >= arr.length) return
  ;[arr[idx], arr[j]] = [arr[j], arr[idx]]
  colOrder.value = arr
  saveColSettings()
}

function resetColSettings() {
  colOrder.value = null
  saveColSettings()
}

function openColumnSettings() {
  if (!props.columnSettings) return
  settingsVisible.value = true
}

onMounted(() => {
  loadColSettings()
})

// 筛选变化防抖：文本输入击键不立即发请求，避免每敲一键一次 API 调用
let queryTimer: ReturnType<typeof setTimeout> | null = null

const titleCol = computed(() => renderCols.value.find((c) => c.asTitle))
const tagCol = computed(() => renderCols.value.find((c) => c.asTag))
const actionCol = computed(() => renderCols.value.find((c) => c.type === 'action'))
const bodyCols = computed(() =>
  renderCols.value.filter((c) => c.type !== 'action' && c !== titleCol.value && c !== tagCol.value),
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
  if (props.expandable) {
    const key = String(row[props.rowKey])
    const next = new Set(expandedKeys.value)
    if (next.has(key)) next.delete(key)
    else next.add(key)
    expandedKeys.value = next
    tableEl.value?.toggleRowExpansion(row)
  }
  emit('row-click', row)
}

/** 切换指定行展开（供操作列"查看"按钮等调用） */
function toggleExpand(row: Record<string, unknown>) {
  if (!props.expandable) return
  const key = String(row[props.rowKey])
  const next = new Set(expandedKeys.value)
  if (next.has(key)) next.delete(key)
  else next.add(key)
  expandedKeys.value = next
  tableEl.value?.toggleRowExpansion(row)
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

defineExpose({ refresh, load, openColumnSettings, toggleExpand })

// 权限判定（避免循环依赖：从全局 store 读取）
import { useUserStore } from '@/stores/user'
const hasPerm = (code?: string) => useUserStore().hasPerm(code)
</script>

<style scoped>
.table-wrap {
  overflow-x: auto;
}
.col-setting-list {
  display: flex;
  flex-direction: column;
  gap: 4px;
  max-height: 55vh;
  overflow: auto;
}
.col-setting-row {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 5px 8px;
  border: 1px solid var(--itsm-border);
  border-radius: 6px;
}
.col-setting-name {
  flex: 1;
  font-size: 13px;
}
.col-setting-actions {
  display: flex;
  gap: 2px;
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
.mobile-expand {
  margin-top: 10px;
  padding-top: 10px;
  border-top: 1px dashed var(--itsm-border);
}
</style>
