<template>
  <div class="login-page">
    <div class="login-card">
      <div class="login-brand">
        <el-icon
          :size="40"
          color="var(--itsm-primary)"
        >
          <Monitor />
        </el-icon>
        <h1>IT运维综合管理系统</h1>
        <p>客户 · 设备 · 巡检 · 工单 · 知识库 一体化管理</p>
      </div>

      <el-form v-if="step === 'password'"
        ref="formRef"
        :model="form"
        :rules="rules"
        size="large"
        @keyup.enter="submit"
      >
        <el-form-item prop="username">
          <el-input
            v-model="form.username"
            placeholder="用户名"
            :prefix-icon="User"
            autocomplete="username"
          />
        </el-form-item>
        <el-form-item prop="password">
          <el-input
            v-model="form.password"
            type="password"
            placeholder="密码"
            :prefix-icon="Lock"
            show-password
            autocomplete="current-password"
          />
        </el-form-item>
        <el-button
          type="primary"
          class="login-btn"
          :loading="loading"
          @click="submit"
        >
          登 录
        </el-button>
      </el-form>

      <el-form v-else size="large" @keyup.enter="submitMfa">
        <el-alert type="info" :closable="false" show-icon
          :title="recovery ? '请输入一次性恢复码' : '请输入腾讯身份验证器中的 6 位登录动态码'" />
        <el-form-item class="mfa-input">
          <el-input v-model="mfaCode" :maxlength="recovery ? 32 : 6"
            :inputmode="recovery ? 'text' : 'numeric'" autocomplete="one-time-code"
            :placeholder="recovery ? '恢复码' : '6 位动态码'" />
        </el-form-item>
        <el-button type="primary" class="login-btn" :loading="loading" @click="submitMfa">验证并登录</el-button>
        <el-button link type="primary" @click="recovery = !recovery">
          {{ recovery ? '使用动态码' : '使用恢复码' }}
        </el-button>
        <el-button link @click="step = 'password'">返回密码登录</el-button>
      </el-form>

      <el-alert
        v-if="errorMsg"
        :title="errorMsg"
        type="error"
        :closable="false"
        class="login-error"
      />
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { User, Lock } from '@element-plus/icons-vue'
import { useUserStore } from '@/stores/user'

const router = useRouter()
const route = useRoute()
const userStore = useUserStore()

const formRef = ref()
const loading = ref(false)
const errorMsg = ref('')
const step = ref<'password' | 'mfa'>('password')
const mfaCode = ref('')
const recovery = ref(false)

const form = reactive({ username: '', password: '' })
const rules = {
  username: [{ required: true, message: '请输入用户名', trigger: 'blur' }],
  password: [{ required: true, message: '请输入密码', trigger: 'blur' }],
}

async function submit() {
  if (loading.value) return
  try {
    await formRef.value?.validate()
  } catch {
    return
  }
  loading.value = true
  errorMsg.value = ''
  try {
    const result = await userStore.login(form.username, form.password)
    if (result.bind_required) {
      await router.push('/mfa')
      return
    }
    if (result.mfa_required) {
      step.value = 'mfa'
      form.password = ''
      return
    }
    const redirect = (route.query.redirect as string) || '/'
    router.push(redirect)
  } catch (e) {
    errorMsg.value = (e as Error).message || '登录失败'
  } finally {
    loading.value = false
  }
}

async function submitMfa() {
  if (loading.value || !mfaCode.value.trim()) return
  loading.value = true
  errorMsg.value = ''
  try {
    await userStore.verifyMfa(mfaCode.value.trim(), recovery.value)
    await router.push((route.query.redirect as string) || '/')
  } catch (e) { errorMsg.value = (e as Error).message || '验证失败' }
  finally { loading.value = false }
}
</script>

<style scoped>
.login-page {
  height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--itsm-brand-backdrop);
  padding: 16px;
}
.login-card {
  width: 380px;
  max-width: 100%;
  background: var(--itsm-card-bg);
  border: 1px solid var(--itsm-border);
  border-radius: 12px;
  padding: 32px 28px;
  box-shadow: var(--itsm-shadow-md);
}
.login-brand {
  text-align: center;
  margin-bottom: 24px;
}
.login-brand h1 {
  font-size: 18px;
  margin: 10px 0 4px;
}
.login-brand p {
  font-size: 12px;
  color: var(--itsm-text-muted);
  margin: 0;
}
.login-btn {
  width: 100%;
  margin-top: 4px;
}
.login-error {
  margin-top: 16px;
}
.mfa-input { margin-top: 16px; }
</style>
