<template>
  <div class="page-container">
    <div class="page-header"><h2 class="page-title">客户服务通知</h2></div><p>展示授权客户的服务安排与最终成果信息，可自愿反馈。</p>
    <el-button @click="load">刷新</el-button>
    <el-card v-for="item in items" :key="item.id" style="margin-top: 12px">
      <h3>{{ item.title }}</h3><p>客户编号：{{ item.customer_id }}</p><p style="white-space: pre-wrap">{{ item.content }}</p>
      <p>{{ new Date(item.created_at).toLocaleString() }}</p>
      <el-tag v-if="item.confirmed_at" type="success">已反馈</el-tag>
      <el-button v-else-if="['ticket_completed', 'inspection_approved'].includes(item.event)" type="primary" @click="confirm(item.id)">反馈（可选）</el-button>
      <p v-if="item.feedback">反馈：{{ item.feedback }}</p>
    </el-card>
    <el-button :disabled="page === 1" @click="page--; load()">上一页</el-button><el-button :disabled="items.length < 50" @click="page++; load()">下一页</el-button>
  </div>
</template>
<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { ElMessageBox } from 'element-plus'
import request from '@/utils/request'
type Item = { id: string; title: string; content: string; customer_id: number; event: string; created_at: string; confirmed_at: string; feedback: string }
const items = ref<Item[]>([]), page = ref(1)
async function load() { items.value = (await request<{ items: Item[] }>({ url: '/api/customer-notifications', params: { page: page.value } })).items }
async function confirm(id: string) {
  const { value } = await ElMessageBox.prompt('可填写不超过 500 字的反馈，不作为验收或服务完成条件。', '服务反馈', { inputType: 'textarea', inputValidator: v => v.length <= 500 || '反馈不得超过 500 字' })
  await request({ url: `/api/customer-notifications/${id}/confirm`, method: 'POST', data: { feedback: value || '' } }); await load()
}
onMounted(load)
</script>
