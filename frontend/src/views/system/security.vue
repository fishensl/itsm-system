<template>
  <div class="page-container security-page">
    <div class="page-header">
      <div>
        <h2 class="page-title">身份与认证安全</h2>
        <p class="page-subtitle">所有强制能力默认关闭。建议先完成用户绑定覆盖，再分项启用。</p>
      </div>
      <el-button type="primary" :loading="saving" @click="save">保存设置</el-button>
    </div>
    <el-card shadow="never">
      <el-form label-width="190px">
        <el-form-item label="强制登录 MFA">
          <el-switch v-model="form.mfa_enforce" />
        </el-form-item>
        <el-form-item label="高风险操作码">
          <el-switch v-model="form.op_code_enforce" />
        </el-form-item>
        <el-form-item label="操作令牌有效期（秒）">
          <el-input-number v-model="form.op_code_ttl_seconds" :min="30" :max="600" />
        </el-form-item>
        <el-form-item label="会话闲置超时（分钟）">
          <el-input-number v-model="form.session_idle_minutes" :min="5" :max="1440" />
        </el-form-item>
        <el-form-item label="会话绑定 IP">
          <el-switch v-model="form.session_bind_ip" />
        </el-form-item>
        <el-divider content-position="left">离职钩子（失败仅告警，不回滚访问撤销）</el-divider>
        <el-form-item label="HTTP Hook URL">
          <el-input v-model="form.offboard_hook_url" placeholder="https://..." />
        </el-form-item>
        <el-form-item label="命令 Hook">
          <el-input v-model="form.offboard_hook_cmd" placeholder="可执行文件及固定参数；不经过 shell" />
        </el-form-item>
      </el-form>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { fetchSystemSecurityProfile, updateSystemSecurityProfile } from '@/api/auth'
import { useUiStore } from '@/stores/ui'

const ui = useUiStore()
const saving = ref(false)
const form = reactive({
  mfa_enforce: false, op_code_enforce: false, op_code_ttl_seconds: 120,
  session_idle_minutes: 30, session_bind_ip: false,
  offboard_hook_url: '', offboard_hook_cmd: '',
})
async function load() {
  const data = await fetchSystemSecurityProfile()
  form.mfa_enforce = data.mfa_enforce === '1'
  form.op_code_enforce = data.op_code_enforce === '1'
  form.session_bind_ip = data.session_bind_ip === '1'
  form.op_code_ttl_seconds = Number(data.op_code_ttl_seconds || 120)
  form.session_idle_minutes = Number(data.session_idle_minutes || 30)
  form.offboard_hook_url = data.offboard_hook_url || ''
  form.offboard_hook_cmd = data.offboard_hook_cmd || ''
}
async function save() {
  saving.value = true
  try { await updateSystemSecurityProfile({ ...form }); ui.toast('安全设置已保存', 'success'); await load() }
  catch (e) { ui.toast((e as Error).message, 'error') }
  finally { saving.value = false }
}
onMounted(() => { load().catch((e) => ui.toast((e as Error).message, 'error')) })
</script>

<style scoped>.security-page { max-width: 900px; margin: 0 auto; }</style>
