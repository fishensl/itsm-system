<template>
  <div class="mobile-filter-panel">
    <button class="filter-toggle" type="button" :aria-expanded="expanded" @click="expanded = !expanded">
      <span>筛选条件<span v-if="activeCount"> · 已选 {{ activeCount }} 项</span></span>
      <span>{{ expanded ? '收起' : '展开' }}</span>
    </button>
    <div class="filter-content" :class="{ 'is-collapsed': !expanded }"><slot /></div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
const props = defineProps<{ filters?: Record<string, unknown> }>()
const expanded = ref(false)
const activeCount = computed(() => Object.values(props.filters || {}).filter(value =>
  value !== '' && value !== undefined && value !== null && value !== false &&
  (!Array.isArray(value) || value.length > 0),
).length)
</script>

<style scoped>
.filter-toggle { display: none; }
@media (max-width: 767px) {
  .filter-toggle {
    display: flex; align-items: center; justify-content: space-between;
    width: 100%; min-height: 44px; margin-bottom: 12px; padding: 10px 12px;
    border: 1px solid var(--itsm-border); border-radius: var(--itsm-radius-md);
    background: var(--itsm-card-bg); color: var(--itsm-text); font: inherit; cursor: pointer;
  }
  .filter-toggle:focus-visible { outline: 2px solid var(--itsm-primary); outline-offset: 2px; }
  .filter-content.is-collapsed { display: none; }
  .filter-content :deep(.filter-row > .el-input),
  .filter-content :deep(.filter-row > .el-select),
  .filter-content :deep(.filter-row > .el-date-editor) { width: 100% !important; min-width: 0; }
}
</style>
