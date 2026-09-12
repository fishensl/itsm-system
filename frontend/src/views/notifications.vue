<template>
  <div class="page-container">
    <div class="page-header"><h2 class="page-title">我的通知</h2></div>
    <div class="filter-row"><el-checkbox v-model="unread" @change="load">只看未读</el-checkbox>
    <el-select v-model="category" clearable placeholder="全部类型" @change="load"><el-option label="工单" value="ticket" /><el-option label="巡检" value="inspection" /><el-option label="审核" value="review" /><el-option label="提醒与摘要" value="system" /></el-select>
    <el-button @click="load">刷新</el-button></div>
    <el-card v-for="item in items" :key="item.id" style="margin-top: 10px">
      <strong>{{ item.title }}</strong><p style="white-space: pre-wrap">{{ item.content }}</p>
      <el-button v-if="!item.is_read" link @click="read(item.id)">标记已读</el-button>
      <router-link v-if="item.link.startsWith('/app/')" :to="item.link.slice(4)">查看详情</router-link>
    </el-card>
    <el-pagination v-model:current-page="page" :page-size="50" :total="total" layout="prev, pager, next" @current-change="load" />
    <h3>订阅设置</h3><el-checkbox v-model="prefs.reminders">待办提醒</el-checkbox><el-checkbox v-model="prefs.daily_digest">每日摘要</el-checkbox><el-checkbox v-model="prefs.weekly_digest">每周摘要</el-checkbox>
    <el-button @click="save">保存</el-button>
  </div>
</template>
<script setup lang="ts">
import { ref, reactive, onMounted } from 'vue'
import request from '@/utils/request'
import { markRead, type NotificationItem } from '@/api/notifications'
const unread = ref(false), category = ref(''), page = ref(1), total = ref(0), items = ref<NotificationItem[]>([])
const prefs = reactive({ reminders: true, daily_digest: false, weekly_digest: false })
async function load() { const r = await request<{ items: NotificationItem[]; total: number }>({ url: '/api/my-notifications', params: { page: page.value, unread: unread.value, category: category.value } }); items.value = r.items; total.value = r.total }
async function read(id: number) { await markRead([id]); await load() }
async function save() { await request({ url: '/api/notification-preferences', method: 'PUT', data: prefs }) }
onMounted(async () => { Object.assign(prefs, await request({ url: '/api/notification-preferences' })); await load() })
</script>
