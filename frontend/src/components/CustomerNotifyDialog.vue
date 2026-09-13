<template>
  <el-dialog v-model="visible" :title="`客户通知 · ${customerName}`" width="640px" class="customer-notify-dialog" destroy-on-close>
    <div v-loading="busy">
      <el-alert title="仅向本客户群发送服务节点，不发送内部审核意见或附件。请核对群成员与客户归属。" type="info" :closable="false" />
      <el-form label-position="left" label-width="88px" style="margin-top: 16px">
        <el-form-item v-if="bindings.length > 1 || (creating && bindings.length)" label="通知群">
          <el-select v-model="selected" @change="selectBinding"><el-option v-for="b in bindings" :key="b.id" :value="b.id" :label="`${b.name} (${b.channel_type})`" /></el-select>
        </el-form-item>
        <el-form-item label="群名称"><div class="notify-group-name"><el-input v-model="name" maxlength="80" /><el-button v-if="!creating" @click="newBinding">新增群</el-button></div></el-form-item>
        <div class="notify-channel-row">
          <el-form-item label="渠道"><el-select v-model="channel" aria-label="渠道"><el-option label="企业微信" value="wecom" /><el-option label="钉钉" value="dingtalk" /><el-option label="飞书" value="feishu" /></el-select></el-form-item>
          <el-form-item :label="bindingLabel"><span>{{ settings.has_wecom_webhook ? '已绑定' : '未绑定' }}</span></el-form-item>
          <el-form-item :label="enabledLabel"><el-switch v-model="enabled" :aria-label="enabledLabel" /></el-form-item>
        </div>
        <el-form-item label="机器人地址">
          <el-input v-model="secret" type="password" autocomplete="new-password" placeholder="已绑定时留空保持不变" />
        </el-form-item>
        <el-form-item v-if="channel !== 'wecom'" label="加签密钥"><el-input v-model="signingSecret" type="password" autocomplete="new-password" placeholder="可选；留空保持原密钥" /></el-form-item>
        <el-form-item label="订阅事件"><el-checkbox-group v-model="subscribed" class="notify-events"><el-checkbox v-for="(label, key) in events" :key="key" :value="key">{{ label }}</el-checkbox></el-checkbox-group></el-form-item>
        <div class="notify-timing-row">
          <el-form-item label="静默时段"><div class="notify-quiet-inputs"><el-input-number v-model="quietStart" :min="0" :max="23" controls-position="right" aria-label="静默开始小时" /><span>至</span><el-input-number v-model="quietEnd" :min="0" :max="23" controls-position="right" aria-label="静默结束小时" /><el-tooltip content="北京时间，开始与结束小时相同则关闭静默" trigger="click"><button type="button" class="notify-help" aria-label="静默时段说明：北京时间，开始与结束小时相同则关闭静默">?</button></el-tooltip></div></el-form-item>
          <el-form-item label="进展合并"><el-select v-model="digestMinutes" aria-label="进展合并"><el-option v-for="n in [0, 5, 15, 30, 60]" :key="n" :value="n" :label="n ? `${n} 分钟` : '关闭'" /></el-select></el-form-item>
        </div>
      </el-form>
      <h4>最近 50 条投递记录</h4>
      <el-table :data="items" max-height="260">
        <el-table-column prop="event" label="事件" />
        <el-table-column label="状态"><template #default="{ row }">{{ statusLabels[row.status] || row.status }}</template></el-table-column>
        <el-table-column label="时间"><template #default="{ row }">{{ row.created_at ? new Date(row.created_at).toLocaleString() : '-' }}</template></el-table-column>
      </el-table>
      <p>接口接受不代表客户已读。临时限流可自动重试；结果未知须先核对群消息，再到通知中心补发。</p>
    </div>
    <template #footer>
      <el-button type="primary" :disabled="busy" @click="save">保存</el-button>
      <el-button :disabled="busy || !settings.has_wecom_webhook || !enabled || dirty" @click="test">发送测试</el-button>
      <el-button type="danger" plain :disabled="busy || !settings.has_wecom_webhook" @click="clear">解绑并停用</el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import request from '@/utils/request'
import { withCredentialEnvelope } from '@/utils/credentialEnvelope'

withDefaults(defineProps<{ enabledLabel?: string; bindingLabel?: string }>(), {
  enabledLabel: '启用通知', bindingLabel: '绑定状态',
})

const visible = ref(false)
const busy = ref(false)
const customerId = ref(0)
const customerName = ref('')
const secret = ref('')
type Binding = { id: number; name: string; channel_type: string; notify_enabled: boolean; has_wecom_webhook: boolean; subscriptions: Record<string, boolean>; quiet_start: number; quiet_end: number; digest_minutes: number }
const bindings = ref<Binding[]>([]), selected = ref<number>(), creating = ref(false)
const name = ref(''), channel = ref('wecom'), signingSecret = ref(''), subscribed = ref<string[]>([])
const defaultGroupName = computed(() => `${customerName.value.trim()}运维服务群`.slice(0, 80))
const quietStart = ref(0), quietEnd = ref(0), digestMinutes = ref(0), events = ref<Record<string, string>>({})
const enabled = ref(false)
const settings = ref({ notify_enabled: false, has_wecom_webhook: false })
const items = ref<{ id: number; event: string; status: string; created_at: string }[]>([])
const statusLabels: Record<string, string> = { accepted: '接口已接受', unknown: '结果未确认', sending: '处理中/待核对', cancelled: '已取消', pending: '待发送', retry: '待重试', failed: '失败' }
const dirty = computed(() => {
  const b = bindings.value.find(item => item.id === selected.value)
  return creating.value || !b || !!secret.value || !!signingSecret.value || name.value !== b.name || channel.value !== b.channel_type || enabled.value !== b.notify_enabled || quietStart.value !== b.quiet_start || quietEnd.value !== b.quiet_end || digestMinutes.value !== b.digest_minutes || Object.keys(events.value).some(k => subscribed.value.includes(k) !== (b.subscriptions[k] ?? k !== 'customer_digest'))
})
const url = () => `/api/customers/${customerId.value}/notify-webhook`
async function refresh() {
  const response = await request<typeof settings.value & { bindings: Binding[]; events: Record<string, string> }>({ url: `/api/customers/${customerId.value}/notify-settings` })
  bindings.value = response.bindings || []
  events.value = response.events || {}
  if (bindings.value.length) {
    if (creating.value) selected.value = bindings.value[bindings.value.length - 1]!.id
    if (!bindings.value.some(b => b.id === selected.value)) selected.value = bindings.value[0]!.id
    selectBinding()
  } else { settings.value = response; enabled.value = response.notify_enabled; newBinding() }
  const result = await request<{ items: typeof items.value }>({ url: `/api/customers/${customerId.value}/notify-deliveries` })
  items.value = result.items
}
async function open(id: number, name: string) {
  customerId.value = id
  customerName.value = name
  secret.value = ''
  selected.value = undefined
  creating.value = false
  items.value = []
  visible.value = true
  busy.value = true
  try { await refresh() } finally { busy.value = false }
}
async function save() {
  busy.value = true
  try {
    const data = { notify_enabled: enabled.value, binding_id: selected.value, create: creating.value, channel_type: channel.value, name: name.value,
      quiet_start: quietStart.value, quiet_end: quietEnd.value, digest_minutes: digestMinutes.value,
      subscriptions: Object.fromEntries(Object.keys(events.value).map(key => [key, subscribed.value.includes(key)])) }
    if (secret.value || signingSecret.value) {
      await withCredentialEnvelope({
        purpose: 'customer.notify.credential.update', binding: { targetId: customerId.value },
        payload: { secret: secret.value, signing_secret: signingSecret.value, binding_id: selected.value },
        execute: ({ requestEnvelope }) => request({ url: url(), method: 'PUT', data: { ...data, credential_envelope: requestEnvelope } }),
        fallback: () => request({ url: url(), method: 'PUT', data: { ...data, wecom_webhook: secret.value, signing_secret: signingSecret.value } }),
      })
    } else await request({ url: url(), method: 'PUT', data })
    secret.value = ''
    signingSecret.value = ''
    await refresh()
    ElMessage.success('通知配置已保存')
  } finally { busy.value = false }
}
async function test() {
  await ElMessageBox.confirm('将向已保存的真实客户群发送一条无业务数据的测试消息。', '发送测试')
  busy.value = true
  try {
    await request({ url: `${url()}/test`, method: 'POST', data: { binding_id: selected.value } })
    ElMessage.info('测试消息已入队，请稍后刷新记录并在群内核对')
    await refresh()
  } finally { busy.value = false }
}
async function clear() {
  await ElMessageBox.confirm('解绑后停止向该客户群发送通知。', '解绑通知')
  busy.value = true
  try {
    await request({ url: url(), method: 'DELETE', data: { binding_id: selected.value } })
    secret.value = ''
    await refresh()
  } finally { busy.value = false }
}
defineExpose({ open })
function selectBinding() {
  const b = bindings.value.find(b => b.id === selected.value)
  if (!b) return
  creating.value = false; name.value = !b.name || b.name === '客户群' ? defaultGroupName.value : b.name; channel.value = b.channel_type; enabled.value = b.notify_enabled
  settings.value = { notify_enabled: b.notify_enabled, has_wecom_webhook: b.has_wecom_webhook }
  subscribed.value = Object.keys(events.value).filter(k => b.subscriptions[k] ?? k !== 'customer_digest')
  quietStart.value = b.quiet_start; quietEnd.value = b.quiet_end; digestMinutes.value = b.digest_minutes
  secret.value = ''; signingSecret.value = ''
}
function newBinding() {
  selected.value = undefined; creating.value = true; name.value = defaultGroupName.value; channel.value = 'wecom'; enabled.value = false
  secret.value = ''; signingSecret.value = ''; quietStart.value = 0; quietEnd.value = 0; digestMinutes.value = 0
  settings.value = { notify_enabled: false, has_wecom_webhook: false }
  subscribed.value = Object.keys(events.value).filter(k => k !== 'customer_digest')
}
</script>

<style>
.customer-notify-dialog .notify-group-name { display: flex; gap: 8px; width: 100%; }
.customer-notify-dialog .notify-group-name .el-input { flex: 1; min-width: 0; }
.customer-notify-dialog .el-form-item { margin-bottom: 14px; }
.customer-notify-dialog .el-form-item__label { justify-content: flex-start; text-align: left; padding-right: 10px; }
.customer-notify-dialog .el-form-item__content { justify-content: flex-start; text-align: left; }
.customer-notify-dialog .el-input__inner { text-align: left; }
.customer-notify-dialog .notify-channel-row { display: flex; flex-wrap: wrap; column-gap: 16px; }
.customer-notify-dialog .notify-channel-row .el-form-item { display: flex; flex-direction: row; align-items: center; min-width: 0; }
.customer-notify-dialog .notify-channel-row .el-form-item__label { flex-shrink: 0; }
.customer-notify-dialog .notify-channel-row .el-form-item:not(:first-child) .el-form-item__label { width: auto !important; padding-right: 8px; }
.customer-notify-dialog .notify-channel-row .el-form-item__content { margin-left: 0 !important; min-width: 0; flex-wrap: nowrap; }
.customer-notify-dialog .notify-channel-row .el-select { width: 124px; flex: none; }
.customer-notify-dialog .notify-channel-row .el-form-item__content > span { white-space: nowrap; }
.customer-notify-dialog .notify-events { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 0 12px; width: 100%; }
.customer-notify-dialog .notify-events .el-checkbox { margin-right: 0; min-width: 0; height: auto; min-height: 32px; white-space: normal; }
.customer-notify-dialog .notify-events .el-checkbox__label { white-space: normal; overflow-wrap: anywhere; line-height: 1.5; }
.customer-notify-dialog .notify-timing-row { display: flex; flex-wrap: wrap; column-gap: 16px; }
.customer-notify-dialog .notify-timing-row .el-form-item { display: flex; align-items: center; }
.customer-notify-dialog .notify-timing-row .el-form-item + .el-form-item .el-form-item__label { width: auto !important; padding-right: 8px; }
.customer-notify-dialog .notify-timing-row .el-form-item__content { margin-left: 0 !important; }
.customer-notify-dialog .notify-timing-row .el-select { width: 96px; flex: none; }
.customer-notify-dialog .notify-quiet-inputs { display: flex; align-items: center; gap: 8px; }
.customer-notify-dialog .notify-quiet-inputs .el-input-number { width: 76px; }
.customer-notify-dialog .notify-help { border: 1px solid var(--el-border-color); border-radius: 50%; width: 20px; height: 20px; padding: 0; color: var(--el-text-color-secondary); background: transparent; cursor: help; }
@media (max-width: 767px) {
  .customer-notify-dialog .notify-channel-row { display: flex; flex-wrap: wrap; column-gap: 16px; }
  .customer-notify-dialog .notify-channel-row .el-form-item:first-child { flex-basis: 100%; }
  .customer-notify-dialog .notify-channel-row .el-form-item__label { padding-right: 8px; }
  .customer-notify-dialog .el-form-item { display: block; }
  .customer-notify-dialog .el-form-item__label { width: auto !important; justify-content: flex-start; }
  .customer-notify-dialog .el-form-item__content { margin-left: 0 !important; gap: 8px; }
  .customer-notify-dialog .notify-events .el-checkbox { min-height: 44px; }
  .customer-notify-dialog .notify-help { min-width: 44px; min-height: 44px; }
}
</style>
