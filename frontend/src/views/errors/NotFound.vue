<template>
  <div class="page-container err-page">
    <div class="err-card">
      <div class="err-code">404</div>
      <h1 class="err-title">页面未找到</h1>
      <p class="err-desc">链接可能已失效，或页面已迁移到新的地址。</p>
      <div class="search-block">
        <span class="search-label">搜索设备、客户、工单或知识库</span>
        <GlobalSearch />
      </div>
      <div class="err-actions">
        <el-button @click="goBack">返回上一页</el-button>
        <el-button type="primary" @click="router.push('/')">返回工作台</el-button>
      </div>
      <div class="err-id">错误标识：ROUTE_NOT_FOUND</div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { useRouter } from 'vue-router'
import GlobalSearch from '@/components/GlobalSearch.vue'

const router = useRouter()

function goBack() {
  if (window.history.length > 1) router.back()
  else router.push('/')
}
</script>

<style scoped>
.err-page {
  min-height: calc(100vh - 32px);
  display: flex;
  align-items: center;
  justify-content: center;
}

.err-card {
  width: min(520px, 100%);
  padding: 40px;
  text-align: center;
  background: var(--itsm-card-bg);
  border: 1px solid var(--itsm-border);
  border-radius: var(--itsm-radius-lg);
}

.err-code {
  color: var(--el-color-primary);
  font-size: 56px;
  font-weight: 700;
  line-height: 1;
}

.err-title {
  margin: 12px 0 6px;
  font-size: 22px;
}

.err-desc,
.search-label,
.err-id {
  color: var(--itsm-text-muted);
}

.search-block {
  display: grid;
  gap: 8px;
  justify-content: center;
  margin: 24px 0;
}

.search-label,
.err-id {
  font-size: var(--itsm-font-xs);
}

.err-actions {
  display: flex;
  justify-content: center;
  gap: var(--itsm-space-2);
}

.err-id {
  margin-top: 20px;
  font-family: ui-monospace, SFMono-Regular, Consolas, monospace;
}

@media (max-width: 767px) {
  .err-card {
    padding: 28px 16px;
  }
}
</style>
