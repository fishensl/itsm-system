<template>
  <div class="page-container security-setup">
    <div class="page-header">
      <div>
        <h2 class="page-title">身份验证器</h2>
        <p class="page-subtitle">使用腾讯身份验证器扫描二维码，登录码与高风险操作码可分别绑定。</p>
      </div>
    </div>
    <el-card shadow="never">
      <el-tabs v-model="purpose">
        <el-tab-pane label="登录验证" name="login" />
        <el-tab-pane label="操作验证" name="operation" />
      </el-tabs>
      <el-result v-if="enabled" icon="success" title="已绑定"
        sub-title="如需更换设备，请使用当前动态码执行换绑。" />
      <template v-else-if="setup">
        <el-alert type="warning" :closable="false" show-icon
          title="恢复码只显示一次。请保存到离线安全位置，不要截图上传或写入浏览器存储。" />
        <div class="bind-grid">
          <img :src="setup.qr_data_uri" alt="腾讯身份验证器绑定二维码" class="qr" />
          <div>
            <p>1. 打开腾讯身份验证器，点击添加账号并扫描二维码。</p>
            <p>2. 无法扫码时手动输入密钥：</p>
            <el-input :model-value="setup.manual_secret" readonly autocomplete="off" />
            <p>3. 输入应用内当前 6 位动态码确认绑定：</p>
            <el-input v-model="code" maxlength="6" inputmode="numeric" autocomplete="one-time-code" />
            <el-button type="primary" :loading="saving" class="mt-2" @click="confirm">确认绑定</el-button>
          </div>
        </div>
        <el-divider>一次性恢复码</el-divider>
        <div class="codes">
          <code v-for="item in setup.backup_codes" :key="item">{{ item }}</code>
        </div>
      </template>
      <el-empty v-else description="尚未绑定">
        <el-button type="primary" :loading="saving" @click="start">开始绑定</el-button>
      </el-empty>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { confirmMfa, fetchMfaStatus, setupMfa, type MfaPurpose, type MfaSetupResult } from '@/api/auth'
import { useUiStore } from '@/stores/ui'

const ui = useUiStore()
const purpose = ref<MfaPurpose>('login')
const status = ref({ login_enabled: false, operation_enabled: false })
const setup = ref<MfaSetupResult>()
const code = ref('')
const saving = ref(false)
const enabled = computed(() => purpose.value === 'login' ? status.value.login_enabled : status.value.operation_enabled)

async function load() { status.value = await fetchMfaStatus() }
async function start() {
  saving.value = true
  try { setup.value = await setupMfa(purpose.value) }
  catch (e) { ui.toast((e as Error).message, 'error') }
  finally { saving.value = false }
}
async function confirm() {
  if (!/^\d{6}$/.test(code.value)) { ui.toast('请输入 6 位动态码', 'warning'); return }
  saving.value = true
  try {
    const result = await confirmMfa(purpose.value, code.value)
    setup.value = undefined
    code.value = ''
    await load()
    ui.toast('绑定成功', 'success')
    if (result?.user) window.location.href = '/app/'
  } catch (e) { ui.toast((e as Error).message, 'error') }
  finally { saving.value = false }
}
watch(purpose, () => { setup.value = undefined; code.value = '' })
onMounted(load)
</script>

<style scoped>
.security-setup { max-width: 860px; margin: 0 auto; }
.bind-grid { display: grid; grid-template-columns: 220px 1fr; gap: 24px; align-items: center; margin-top: 20px; }
.qr { width: 220px; height: 220px; }
.codes { display: grid; grid-template-columns: repeat(4, 1fr); gap: 10px; }
.codes code { padding: 8px; text-align: center; background: var(--el-fill-color-light); border-radius: 4px; }
@media (max-width: 640px) { .bind-grid { grid-template-columns: 1fr; } .codes { grid-template-columns: repeat(2, 1fr); } }
</style>
