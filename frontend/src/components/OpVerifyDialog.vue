<template>
  <el-dialog v-model="visible" title="高风险操作验证" width="420px" destroy-on-close
    :close-on-click-modal="false" @closed="cancel">
    <el-alert type="warning" :closable="false" show-icon
      title="请输入腾讯身份验证器中的操作动态码。验证后短时间内无需重复输入。" />
    <el-input v-model="code" maxlength="6" inputmode="numeric" autocomplete="one-time-code"
      placeholder="6 位动态码" class="mt-2" @keyup.enter="submit" />
    <template #footer>
      <el-button @click="visible = false">取消</el-button>
      <el-button type="primary" :loading="loading" @click="submit">验证</el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref } from 'vue'
import { verifyOperationCode } from '@/api/auth'
import { cancelOperationVerification, completeOperationVerification } from '@/utils/operationToken'
import { useUiStore } from '@/stores/ui'

const ui = useUiStore()
const visible = ref(false)
const loading = ref(false)
const code = ref('')
function open() { code.value = ''; visible.value = true }
function cancel() { if (!loading.value) cancelOperationVerification() }
async function submit() {
  if (!/^\d{6}$/.test(code.value)) { ui.toast('请输入 6 位动态码', 'warning'); return }
  loading.value = true
  try {
    const result = await verifyOperationCode(code.value)
    completeOperationVerification(result.token, result.expires_in)
    visible.value = false
  } catch (e) { ui.toast((e as Error).message, 'error') }
  finally { loading.value = false }
}
onMounted(() => window.addEventListener('itsm:op-verify-request', open))
onBeforeUnmount(() => window.removeEventListener('itsm:op-verify-request', open))
</script>
