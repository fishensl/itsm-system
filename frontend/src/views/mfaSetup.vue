<template>
  <div class="page-container security-setup">
    <div class="page-header">
      <div>
        <h2 class="page-title">身份验证器</h2>
        <p class="page-subtitle">一个账号只绑定一个身份验证器，同时用于登录和高风险操作再次确认。</p>
      </div>
    </div>

    <el-alert
      v-if="status.binding_required"
      class="bind-required-alert"
      type="warning"
      :closable="false"
      show-icon
      title="首次登录必须先绑定账号 MFA"
      description="请使用腾讯身份验证器扫码并输入 6 位动态码。绑定成功后，系统会继续引导你修改初始密码。"
    />

    <el-card shadow="never" class="status-card">
      <div class="account-status">
        <span class="purpose-main">
          <span class="purpose-title">账号 MFA</span>
          <span class="purpose-desc">登录时验证；查看设备密码等高风险操作时复用同一个 6 位动态码</span>
        </span>
        <el-tag :type="enabled ? 'success' : 'warning'" effect="light">
          {{ enabled ? '已绑定' : '未绑定' }}
        </el-tag>
      </div>
    </el-card>

    <el-card shadow="never" class="bind-card">
      <template #header>
        <div class="card-header">
          <div>
            <div class="card-title">账号 MFA</div>
            <div class="card-subtitle">同一绑定保护登录，并为查看密码等高风险操作提供再次验证</div>
          </div>
          <el-tag v-if="statusLoaded" :type="enabled ? 'success' : 'warning'">
            {{ enabled ? '已绑定' : '等待绑定' }}
          </el-tag>
        </div>
      </template>

      <el-skeleton v-if="!statusLoaded" :rows="4" animated />

      <template v-else-if="setup">
        <el-alert
          type="warning"
          :closable="false"
          show-icon
          title="恢复码只显示一次，请保存到离线安全位置，不要截图上传或写入浏览器存储。"
        />
        <div class="bind-grid">
          <div class="qr-panel">
            <img :src="setup.qr_data_uri" alt="腾讯身份验证器绑定二维码" class="qr" />
            <span class="qr-caption">使用腾讯身份验证器扫码</span>
          </div>
          <div class="bind-steps">
            <div class="step-row">
              <span class="step-no">1</span>
              <span>打开腾讯身份验证器，点击“添加账号”并扫描左侧二维码。</span>
            </div>
            <div class="step-row">
              <span class="step-no">2</span>
              <div class="step-content">
                <span>无法扫码时，手动输入以下密钥：</span>
                <el-input :model-value="setup.manual_secret" readonly autocomplete="off" />
              </div>
            </div>
            <div class="step-row">
              <span class="step-no">3</span>
              <div class="step-content">
                <span>输入应用中当前显示的 6 位动态码完成绑定：</span>
                <div class="confirm-row">
                  <el-input
                    v-model="code"
                    maxlength="6"
                    inputmode="numeric"
                    autocomplete="one-time-code"
                    placeholder="6 位动态码"
                    @keyup.enter="confirm"
                  />
                  <el-button type="primary" :loading="saving" @click="confirm">确认绑定</el-button>
                  <el-button @click="cancelSetup">取消</el-button>
                </div>
              </div>
            </div>
          </div>
        </div>

        <el-divider content-position="left">一次性恢复码</el-divider>
        <div class="codes">
          <code v-for="item in setup.backup_codes" :key="item">{{ item }}</code>
        </div>
      </template>

      <el-result
        v-else-if="enabled"
        icon="success"
        title="账号 MFA 已绑定"
        sub-title="登录和高风险操作均使用这一身份验证器。更换手机或重新安装时，请先完成换绑。"
      >
        <template #extra>
          <el-button type="primary" plain @click="rebindVisible = true">更换绑定</el-button>
        </template>
      </el-result>

      <el-empty v-else description="账号 MFA 尚未绑定">
        <el-button type="primary" :loading="saving" @click="start">立即绑定</el-button>
        <p class="empty-hint">绑定过程只需扫码并输入一次 6 位动态码。</p>
      </el-empty>
    </el-card>

    <el-dialog v-model="rebindVisible" title="验证当前身份后换绑" width="440px" destroy-on-close>
      <el-alert
        type="info"
        :closable="false"
        show-icon
        title="请输入当前动态码；身份验证器不可用时也可输入一条恢复码。"
      />
      <el-form label-position="top" class="rebind-form" @submit.prevent>
        <el-form-item label="当前动态码或恢复码">
          <el-input
            v-model="currentCode"
            autocomplete="one-time-code"
            placeholder="输入当前动态码或恢复码"
            @keyup.enter="beginRebind"
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="rebindVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="beginRebind">验证并生成新二维码</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import {
  confirmMfa,
  fetchMfaStatus,
  rebindMfa,
  setupMfa,
  type MfaSetupResult,
} from '@/api/auth'
import { useUserStore } from '@/stores/user'
import { useUiStore } from '@/stores/ui'

const ui = useUiStore()
const user = useUserStore()
const status = ref({ account_enabled: false, login_enabled: false, operation_enabled: false,
  operation_uses_account_mfa: true,
  binding_required: false, backup_codes_remaining: 0 })
const statusLoaded = ref(false)
const setup = ref<MfaSetupResult>()
const code = ref('')
const saving = ref(false)
const rebindVisible = ref(false)
const currentCode = ref('')

const enabled = computed(() => status.value.account_enabled || status.value.login_enabled)

async function load() {
  try {
    status.value = await fetchMfaStatus()
  } finally {
    statusLoaded.value = true
  }
}

async function start() {
  saving.value = true
  try {
    setup.value = await setupMfa()
  } catch (error) {
    ui.toast((error as Error).message, 'error')
  } finally {
    saving.value = false
  }
}

function cancelSetup() {
  setup.value = undefined
  code.value = ''
}

async function confirm() {
  if (!/^\d{6}$/.test(code.value)) {
    ui.toast('请输入 6 位动态码', 'warning')
    return
  }
  saving.value = true
  try {
    const result = await confirmMfa(code.value)
    cancelSetup()
    await load()
    if (user.user) user.user.mfa_enabled = true
    ui.toast('绑定成功', 'success')
    if (result?.user) window.location.href = '/app/'
  } catch (error) {
    ui.toast((error as Error).message, 'error')
  } finally {
    saving.value = false
  }
}

async function beginRebind() {
  if (!currentCode.value.trim()) {
    ui.toast('请输入当前动态码或恢复码', 'warning')
    return
  }
  saving.value = true
  try {
    setup.value = await rebindMfa(currentCode.value.trim())
    currentCode.value = ''
    code.value = ''
    rebindVisible.value = false
    ui.toast('身份验证通过，请扫描新二维码完成换绑', 'success')
  } catch (error) {
    ui.toast((error as Error).message, 'error')
  } finally {
    saving.value = false
  }
}

onMounted(() => {
  load().catch((error) => ui.toast((error as Error).message, 'error'))
})
</script>

<style scoped>
.security-setup { max-width: 920px; margin: 0 auto; }
.bind-required-alert, .status-card { margin-bottom: 14px; }
.account-status {
  display: flex; align-items: center; justify-content: space-between; gap: 16px;
  width: 100%; padding: 16px; color: var(--itsm-text); text-align: left;
  background: var(--itsm-card-bg); border: 1px solid var(--itsm-border); border-radius: 10px;
}
.purpose-main { display: flex; flex-direction: column; gap: 4px; }
.purpose-title { font-size: 15px; font-weight: 600; }
.purpose-desc, .card-subtitle, .empty-hint, .qr-caption { color: var(--itsm-text-muted); font-size: 12px; }
.card-header { display: flex; justify-content: space-between; align-items: center; gap: 16px; }
.card-title { font-size: 15px; font-weight: 600; }
.card-subtitle { margin-top: 4px; }
.bind-grid { display: grid; grid-template-columns: 230px minmax(0, 1fr); gap: 28px; align-items: center; margin-top: 20px; }
.qr-panel { display: flex; flex-direction: column; align-items: center; gap: 8px; }
.qr { width: 220px; height: 220px; border: 1px solid var(--itsm-border); border-radius: 8px; }
.bind-steps { display: flex; flex-direction: column; gap: 18px; }
.step-row { display: flex; align-items: flex-start; gap: 10px; line-height: 1.6; }
.step-no {
  display: inline-flex; align-items: center; justify-content: center; flex: 0 0 24px;
  width: 24px; height: 24px; color: var(--itsm-text-inverse); font-size: 12px; font-weight: 700;
  background: var(--el-color-primary); border-radius: 50%;
}
.step-content { display: flex; flex: 1; flex-direction: column; gap: 8px; min-width: 0; }
.confirm-row { display: grid; grid-template-columns: minmax(120px, 1fr) auto auto; gap: 8px; }
.codes { display: grid; grid-template-columns: repeat(4, 1fr); gap: 10px; }
.codes code { padding: 9px; text-align: center; background: var(--el-fill-color-light); border-radius: 6px; }
.empty-hint { margin: 10px 0 0; }
.rebind-form { margin-top: 16px; }
@media (max-width: 680px) {
  .bind-grid { grid-template-columns: 1fr; }
  .confirm-row { grid-template-columns: 1fr; }
  .codes { grid-template-columns: repeat(2, 1fr); }
}
</style>
