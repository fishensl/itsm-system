<template>
  <el-popover v-model:visible="visible" placement="bottom-end" :width="420" trigger="manual" popper-class="search-popover">
    <template #reference>
      <div class="search-wrap" @click.stop>
        <el-input
          v-model="keyword"
          placeholder="搜索设备/客户/工单/知识库..."
          :prefix-icon="Search"
          clearable
          @input="onInput"
          @focus="onFocus"
        />
      </div>
    </template>
    <div v-loading="loading" class="search-panel">
      <template v-if="keyword">
        <div v-for="grp in groups" :key="grp.key" class="search-group">
          <div v-if="grp.items.length" class="search-group-title">{{ grp.label }}</div>
          <div
            v-for="it in grp.items"
            :key="grp.key + it.id"
            class="search-item"
            @click="go(grp.key, it.id)"
          >
            <span class="search-item-title">{{ it.title }}</span>
            <span class="search-item-sub">{{ it.sub }}</span>
          </div>
        </div>
        <div v-if="!loading && !hasAny" class="search-empty">未找到「{{ keyword }}」相关内容</div>
      </template>
      <div v-else class="search-hint">输入至少 2 个字符搜索</div>
    </div>
  </el-popover>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onBeforeUnmount } from 'vue'
import { useRouter } from 'vue-router'
import { Search } from '@element-plus/icons-vue'
import request from '@/utils/request'

interface SearchResult {
  devices: { id: number; title: string; sub: string }[]
  customers: { id: number; title: string; sub: string }[]
  tickets: { id: number; title: string; sub: string }[]
  knowledge: { id: number; title: string; sub: string }[]
}

const router = useRouter()
const keyword = ref('')
const visible = ref(false)
const loading = ref(false)
const results = ref<SearchResult>({ devices: [], customers: [], tickets: [], knowledge: [] })

const groups = computed(() => [
  { key: 'devices', label: '设备', items: results.value.devices },
  { key: 'customers', label: '客户', items: results.value.customers },
  { key: 'tickets', label: '工单', items: results.value.tickets },
  { key: 'knowledge', label: '知识库', items: results.value.knowledge },
])
const hasAny = computed(
  () => ['devices', 'customers', 'tickets', 'knowledge'].some((k) => results.value[k as keyof SearchResult].length > 0),
)

let timer: ReturnType<typeof setTimeout> | undefined

function onInput() {
  clearTimeout(timer)
  if (keyword.value.trim().length < 2) {
    visible.value = false
    return
  }
  timer = setTimeout(doSearch, 300)
}

function onFocus() {
  if (keyword.value.trim().length >= 2) doSearch()
}

async function doSearch() {
  loading.value = true
  visible.value = true
  try {
    results.value = await request<SearchResult>({
      url: '/api/search',
      method: 'GET',
      params: { q: keyword.value.trim() },
    })
  } catch {
    /* toast */
  } finally {
    loading.value = false
  }
}

function go(type: string, id: number) {
  const pathMap: Record<string, string> = {
    devices: '/app/devices/',
    customers: '/app/customers/',
    tickets: '/app/tickets/',
    knowledge: '/app/knowledge/',
  }
  visible.value = false
  router.push(`${pathMap[type]}${id}`)
}

function onDocClick() {
  visible.value = false
}

onMounted(() => document.addEventListener('click', onDocClick))
onBeforeUnmount(() => {
  document.removeEventListener('click', onDocClick)
  clearTimeout(timer)
})
</script>

<style scoped>
.search-wrap {
  display: inline-flex;
}
.search-panel {
  max-height: 420px;
  overflow-y: auto;
}
.search-group-title {
  font-size: 12px;
  color: var(--itsm-text-muted);
  padding: 6px 8px 2px;
  font-weight: 600;
}
.search-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 7px 8px;
  border-radius: 6px;
  cursor: pointer;
  font-size: 13px;
}
.search-item:hover {
  background: var(--el-fill-color-light);
}
.search-item-title {
  font-weight: 500;
}
.search-item-sub {
  color: var(--itsm-text-muted);
  font-size: 12px;
  margin-left: auto;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  max-width: 200px;
}
.search-empty,
.search-hint {
  padding: 16px;
  text-align: center;
  color: var(--itsm-text-muted);
  font-size: 13px;
}
</style>
