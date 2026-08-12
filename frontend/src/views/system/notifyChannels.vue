<template>
  <div class="page-container">
    <div class="page-header">
      <h2 class="page-title">通知渠道</h2>
    </div>

    <el-row v-if="channels.length" :gutter="12">
      <el-col v-for="ch in channels" :key="ch.channel_type" :xs="24" :md="12" :lg="8">
        <el-card shadow="never" class="channel-card">
          <template #header>
            <div class="ch-head">
              <span class="ch-name">{{ channelLabel(ch.channel_type) }}</span>
              <el-switch v-model="ch.is_enabled" :loading="savingType === ch.channel_type"
                @change="(v: boolean | string | number) => toggle(ch, !!v)" />
            </div>
          </template>

          <el-form label-width="92px" size="small">
            <el-form-item label="应用名称">
              <el-input v-model="ch.name" placeholder="渠道显示名" />
            </el-form-item>
            <template v-if="ch.channel_type === 'wecom'">
              <el-form-item label="企业 ID">
                <el-input v-model="ch.config.corpid" placeholder="CorpID" />
              </el-form-item>
              <el-form-item label="应用 AgentId">
                <el-input v-model="ch.config.agent_id" placeholder="自建应用 AgentId" />
              </el-form-item>
              <el-form-item label="应用 Secret">
                <el-input v-model="secretInputs[ch.channel_type]" type="password" show-password autocomplete="new-password"
                  :placeholder="ch.has_secret ? '已配置，留空不修改' : '必填'" />
              </el-form-item>
            </template>
            <template v-else-if="ch.channel_type === 'dingtalk'">
              <el-form-item label="AppKey">
                <el-input v-model="ch.config.app_key" placeholder="钉钉自建应用 AppKey" />
              </el-form-item>
              <el-form-item label="AgentId">
                <el-input v-model="ch.config.agent_id" placeholder="钉钉应用 AgentId" />
              </el-form-item>
              <el-form-item label="AppSecret">
                <el-input v-model="secretInputs[ch.channel_type]" type="password" show-password autocomplete="new-password"
                  :placeholder="ch.has_secret ? '已配置，留空不修改' : '必填'" />
              </el-form-item>
            </template>
            <template v-else-if="ch.channel_type === 'feishu'">
              <el-form-item label="App ID">
                <el-input v-model="ch.config.app_id" placeholder="飞书自建应用 App ID" />
              </el-form-item>
              <el-form-item label="App Secret">
                <el-input v-model="secretInputs[ch.channel_type]" type="password" show-password autocomplete="new-password"
                  :placeholder="ch.has_secret ? '已配置，留空不修改' : '必填'" />
              </el-form-item>
            </template>
          </el-form>

          <div class="ch-actions">
            <el-button type="primary" size="small" :loading="savingType === ch.channel_type"
              @click="saveChannel(ch)">保存配置</el-button>
          </div>

          <el-divider content-position="left">发送测试</el-divider>
          <div class="test-row">
            <el-input v-model="testAccounts[ch.channel_type]" size="small" class="test-account"
              :placeholder="channelTestHint(ch.channel_type)" />
            <el-select v-model="testModes[ch.channel_type]" size="small" class="test-mode">
              <el-option label="文本" value="text" />
              <el-option label="Markdown" value="markdown" />
              <el-option label="文件" value="file" />
            </el-select>
            <el-button size="small" :loading="testingType === ch.channel_type"
              @click="sendTest(ch)">发送测试</el-button>
          </div>
          <p class="test-hint">{{ channelTestHint(ch.channel_type) }}</p>
        </el-card>
      </el-col>
    </el-row>
    <el-empty v-else description="尚未配置通知渠道，系统初始化后自动出现 企业微信 / 钉钉 / 飞书 三个渠道"
      :image-size="80" />
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted } from 'vue'
import { useUiStore } from '@/stores/ui'
import {
  fetchNotifyChannels, saveNotifyChannel, testNotifyChannel,
  type NotifyChannelItem,
} from '@/api/system'

const ui = useUiStore()
const channels = ref<NotifyChannelItem[]>([])
const secretInputs = reactive<Record<string, string>>({})
const testAccounts = reactive<Record<string, string>>({})
const testModes = reactive<Record<string, string>>({ wecom: 'text', dingtalk: 'text', feishu: 'text' })
const savingType = ref('')
const testingType = ref('')

const LABELS: Record<string, string> = { wecom: '企业微信', dingtalk: '钉钉', feishu: '飞书' }
const HINTS: Record<string, string> = {
  wecom: '接收测试的企业微信账号（userid，开启通讯录同步后=企业账号）',
  dingtalk: '接收测试的钉钉账号（手机号或 userid）',
  feishu: '接收测试的飞书账号（手机号或 user_id/open_id）',
}

function channelLabel(t: string) { return LABELS[t] || t }
function channelTestHint(t: string) { return HINTS[t] || '接收测试的渠道账号' }

onMounted(async () => {
  try {
    const res = await fetchNotifyChannels()
    channels.value = res.channels
  } catch { /* toast by interceptor */ }
})

function payloadFor(ch: NotifyChannelItem) {
  const secretKey = ch.channel_type === 'wecom' ? 'secret'
    : ch.channel_type === 'dingtalk' ? 'app_secret' : 'app_secret'
  const config = { ...ch.config }
  const s = secretInputs[ch.channel_type] || ''
  if (s) (config as Record<string, string>)[secretKey] = s
  return { name: ch.name, is_enabled: ch.is_enabled, config }
}

async function saveChannel(ch: NotifyChannelItem) {
  savingType.value = ch.channel_type
  try {
    await saveNotifyChannel(ch.channel_type, payloadFor(ch))
    ui.toast('渠道配置已保存', 'success')
    const res = await fetchNotifyChannels()
    channels.value = res.channels
  } catch (e) {
    ui.toast((e as Error).message, 'error')
  } finally {
    savingType.value = ''
  }
}

async function toggle(ch: NotifyChannelItem, v: boolean) {
  savingType.value = ch.channel_type
  try {
    await saveNotifyChannel(ch.channel_type, { ...payloadFor(ch), is_enabled: v })
    ui.toast(`「${channelLabel(ch.channel_type)}」已${v ? '启用' : '停用'}`, 'success')
  } catch (e) {
    ui.toast((e as Error).message, 'error')
    ch.is_enabled = !v
  } finally {
    savingType.value = ''
  }
}

async function sendTest(ch: NotifyChannelItem) {
  const account = testAccounts[ch.channel_type] || ''
  if (!account) { ui.toast('请填写接收测试消息的渠道账号', 'warning'); return }
  testingType.value = ch.channel_type
  try {
    await testNotifyChannel(ch.channel_type, account, testModes[ch.channel_type] || 'text')
    ui.toast('测试消息发送成功，请在渠道端确认', 'success')
  } catch (e) {
    ui.toast((e as Error).message, 'error')
  } finally {
    testingType.value = ''
  }
}
</script>

<style scoped>
.channel-card { margin-bottom: 12px; }
.ch-head { display: flex; justify-content: space-between; align-items: center; }
.ch-name { font-weight: 600; }
.ch-actions { display: flex; gap: 8px; }
.test-row { display: flex; gap: 8px; }
.test-account { flex: 1; }
.test-mode { width: 110px; }
.test-hint { color: var(--itsm-text-muted); font-size: 12px; margin-top: 6px; }
</style>
