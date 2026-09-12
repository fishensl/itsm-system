<template>
  <el-collapse @change="load">
    <el-collapse-item title="通知记录" name="history">
      <div v-loading="loading">
        <el-empty v-if="!items.length" description="暂无投递记录" :image-size="50" />
        <p v-for="item in items" :key="item.id">{{ item.event }} · {{ item.audience === 'customer' ? '客户' : '内部' }} · {{ item.channel }} · {{ labels[item.status] || item.status }} · {{ new Date(item.created_at).toLocaleString() }} <span v-if="item.error_code">（{{ item.error_code }}）</span></p>
        <el-pagination v-if="total > 20" v-model:current-page="page" :page-size="20" :total="total" layout="prev, pager, next" @current-change="fetchPage" />
      </div>
    </el-collapse-item>
  </el-collapse>
</template>
<script setup lang="ts">
import { ref } from 'vue'
import request from '@/utils/request'
const props = defineProps<{ entityType: string; entityId: number }>()
type Item = { id: number; event: string; audience: string; channel: string; status: string; created_at: string; error_code: string }
const items = ref<Item[]>([]), page = ref(1), total = ref(0), loading = ref(false)
const labels: Record<string, string> = { pending: '待发送', sending: '发送中', accepted: '接口已接受', retry: '待重试', failed: '失败', unknown: '结果未知', cancelled: '已取消' }
async function fetchPage() {
  loading.value = true
  try {
    const result = await request<{ items: Item[]; total: number }>({ url: '/api/notify-center', params: { entity_type: props.entityType, entity_id: props.entityId, page: page.value, page_size: 20 } })
    items.value = result.items; total.value = result.total
  } finally { loading.value = false }
}
function load(open: string | number | (string | number)[]) { if (Array.isArray(open) && open.length) void fetchPage() }
</script>
