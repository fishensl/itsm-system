<template>
  <div class="page-container">
    <div class="page-header"><h2 class="page-title">通知中心</h2></div>
    <el-alert :title="metrics.worker_healthy ? '发送服务运行中' : '发送服务心跳异常，请检查独立通知服务'" :type="metrics.worker_healthy ? 'success' : 'warning'" :closable="false" />
    <p>接口已接受不等于客户已读。结果未知的补发可能重复，请先核对真实群消息。</p>
    <div class="filter-row"><el-select v-model="status" clearable placeholder="全部状态"><el-option v-for="(label, key) in labels" :key="key" :label="label" :value="key" /></el-select>
    <el-button @click="reload">刷新</el-button></div>
    <span v-for="(count, key) in metrics.counts" :key="key" style="margin: 8px">{{ labels[key] || key }}：{{ count }}</span>
    <p v-if="metrics.oldest_pending">最早待发：{{ new Date(metrics.oldest_pending).toLocaleString() }}</p>
    <p v-if="metrics.accepted_rate != null">已结束投递的接口接受率：{{ metrics.accepted_rate }}%</p>
    <p v-if="metrics.average_delivery_seconds != null">平均投递耗时（含排队）：{{ metrics.average_delivery_seconds }} 秒</p>
    <el-collapse><el-collapse-item title="按渠道与客户统计" name="statistics"><div class="notification-statistics"><div><h3>渠道</h3><p v-for="r in metrics.by_channel" :key="`${r.key}:${r.status}`">{{ r.key }} · {{ labels[r.status] }}：{{ r.count }}</p></div><div><h3>客户</h3><p v-for="r in metrics.by_customer" :key="`${r.key}:${r.status}`">{{ r.key ? `客户 #${r.key}` : '内部' }} · {{ labels[r.status] }}：{{ r.count }}</p></div></div></el-collapse-item></el-collapse>
    <DataTable ref="table" :columns="columns" :fetch-data="fetchPage" :query="deliveryQuery" row-key="id" :column-settings="{ storageKey: 'cols_notification_delivery' }">
      <template #cell-status="{ row }">{{ labels[row.status] || row.status }}</template>
      <template #cell-actions="{ row }">
        <el-button link @click="attempts(row.id)">尝试记录</el-button>
        <el-button v-if="user.hasPerm('notify:edit') && ['failed', 'unknown'].includes(row.status)" link type="primary" @click="retry(row)">补发</el-button>
      </template>
    </DataTable>
    <el-divider />
    <el-collapse v-if="user.hasPerm('notify:edit')" class="notification-section">
      <el-collapse-item title="管理提醒规则与通知模板" name="settings">
        <NotificationPolicy />
        <NotificationTemplates class="notification-section" />
      </el-collapse-item>
    </el-collapse>
    <h3>个人订阅</h3>
    <el-checkbox v-model="prefs.reminders">待办提醒</el-checkbox><el-checkbox v-model="prefs.daily_digest">日报</el-checkbox><el-checkbox v-model="prefs.weekly_digest">周报（周一）</el-checkbox>
    <el-button @click="savePrefs">保存订阅</el-button>
    <template v-if="user.hasPerm('customer:notify')">
      <h3>发布客户可见进展</h3>
      <el-alert title="请填写可向客户公开的内容，不要包含密码、配置或内部审核意见。发布后会按客户的各群订阅发送。" :closable="false" />
      <el-select v-model="progress.entity_type"><el-option label="工单" value="ticket" /><el-option label="巡检任务" value="task" /></el-select>
      <el-input-number v-model="progress.entity_id" :min="1" /><el-input v-model="progress.content" type="textarea" maxlength="500" show-word-limit placeholder="客户可见进展" />
      <el-button type="primary" @click="publish">确认公开并发布</el-button>
    </template>
    <el-dialog v-model="attemptVisible" title="投递尝试"><el-table :data="attemptRows"><el-table-column prop="number" label="次数" /><el-table-column prop="result" label="结果" /><el-table-column prop="error_code" label="原因" /><el-table-column prop="created_at" label="时间" /></el-table></el-dialog>
  </div>
</template>
<script setup lang="ts">
import { ref, reactive, computed, onMounted } from 'vue'
import { ElMessageBox, ElMessage } from 'element-plus'
import request from '@/utils/request'
import { useUserStore } from '@/stores/user'
import NotificationPolicy from '@/components/NotificationPolicy.vue'
import NotificationTemplates from '@/components/NotificationTemplates.vue'
import DataTable, { type DataColumn } from '@/components/DataTable.vue'
import { fetchEntityMeta, type EntityMeta } from '@/api/meta'
const table = ref<InstanceType<typeof DataTable>>()
const metadata = ref<EntityMeta>()
const columns = computed<DataColumn[]>(() => [...(metadata.value?.profiles.list || []).map(f => ({ key: f.key, label: f.label, width: f.width, minWidth: f.minWidth, asTitle: f.key === 'event' })), { key: 'actions', label: '操作', minWidth: 160 }])
const user = useUserStore()
type Delivery = { id: number; status: string; event: string; channel: string; attempts: number; target: string; error_code: string; customer_id: number | null }
const labels: Record<string, string> = { pending: '待发送', sending: '发送中', accepted: '接口已接受', retry: '待重试', failed: '最终失败', unknown: '结果未知', cancelled: '已取消' }
const status = ref('')
// Metrics update on every response; keep query identity stable until the filter changes.
const deliveryQuery = computed(() => ({ status: status.value }))
const metrics = ref<{ worker_healthy: boolean; oldest_pending?: string; accepted_rate?: number | null; average_delivery_seconds?: number | null; by_channel?: { key: string; status: string; count: number }[]; by_customer?: { key: number | null; status: string; count: number }[]; counts: Record<string, number> }>({ worker_healthy: false, counts: {} })
const prefs = reactive({ reminders: true, daily_digest: false, weekly_digest: false })
const progress = reactive({ entity_type: 'ticket', entity_id: 1, content: '' })
const attemptVisible = ref(false), attemptRows = ref<Record<string, unknown>[]>([])
async function fetchPage(params: Record<string, unknown>) {
  const [r, meta] = await Promise.all([
    request<{ items: Delivery[]; total: number; page: number; page_size: number; metrics: typeof metrics.value }>({ url: '/api/notify-center', params }),
    fetchEntityMeta('notification_delivery'),
  ])
  metadata.value = meta; metrics.value = r.metrics
  return r
}
async function reload() { await table.value?.refresh() }
async function retry(row: { id: number; status: string } | Record<string, any>) {
  await ElMessageBox.confirm(row.status === 'unknown' ? '该消息可能已发送。确认补发可能造成重复消息，是否继续？' : '确认重新投递此消息？', '人工补发')
  await request({ url: `/api/notify-center/${row.id}/retry`, method: 'POST', data: { acknowledge_unknown: true } }); await reload()
}
async function attempts(id: number) {
  attemptRows.value = (await request<{ items: Record<string, unknown>[] }>({ url: `/api/notify-center/${id}/attempts` })).items
  attemptVisible.value = true
}
async function savePrefs() { await request({ url: '/api/notification-preferences', method: 'PUT', data: prefs }); ElMessage.success('已保存') }
async function publish() {
  await ElMessageBox.confirm('确认以上内容可以公开给客户并发送到真实群？', '发布进展')
  await request({ url: '/api/customer-progress', method: 'POST', data: { ...progress, confirm_public: true } }); progress.content = ''; await reload()
}
onMounted(async () => { Object.assign(prefs, await request({ url: '/api/notification-preferences' })) })
</script>

<style scoped>
.notification-statistics { display: flex; flex-wrap: wrap; gap: var(--itsm-space-6); }
</style>
