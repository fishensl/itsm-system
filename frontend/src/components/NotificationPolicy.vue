<template>
  <el-card shadow="never" class="section-card">
    <template #header>提醒与升级规则</template>
    <el-form label-position="top" class="notification-policy-grid">
      <el-form-item label="每日提醒时间（北京时间）"><div class="filter-row"><el-input-number v-model="policy.hour" :min="0" :max="23" aria-label="提醒小时" />时 <el-input-number v-model="policy.minute" :min="0" :max="59" aria-label="提醒分钟" />分</div></el-form-item>
      <el-form-item label="审核等待天数"><el-input-number v-model="policy.review_days" :min="1" :max="90" /></el-form-item>
      <el-form-item label="升级等待天数"><el-input-number v-model="policy.escalation_days" :min="1" :max="90" /></el-form-item>
      <el-form-item label="升级对象"><el-checkbox v-model="policy.escalate_supervisor">部门主管</el-checkbox><el-checkbox v-model="policy.escalate_admin">管理员</el-checkbox></el-form-item>
      <el-form-item label="额外升级对象"><el-select v-model="policy.extra_user_ids" multiple filterable clearable><el-option v-for="u in users" :key="u.id" :value="u.id" :label="u.name" /></el-select></el-form-item>
    </el-form>
    <el-button type="primary" :loading="saving" @click="save">保存提醒规则</el-button>
  </el-card>
</template>
<script setup lang="ts">
import { reactive, ref, onMounted } from 'vue'
import request from '@/utils/request'
import { ElMessage } from 'element-plus'
import { fetchNotifyRules } from '@/api/system'
const policy = reactive({ hour: 8, minute: 30, review_days: 3, escalation_days: 3, escalate_supervisor: true, escalate_admin: true, extra_user_ids: [] as number[] })
const users = ref<{ id: number; name: string }[]>([]), saving = ref(false)
onMounted(async () => { const [data, rules] = await Promise.all([request({ url: '/api/notification-policy' }), fetchNotifyRules()]); Object.assign(policy, data); users.value = rules.user_options })
async function save() { saving.value = true; try { await request({ url: '/api/notification-policy', method: 'PUT', data: policy }); ElMessage.success('提醒规则已保存') } finally { saving.value = false } }
</script>
<style scoped>
.notification-policy-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(min(100%, 260px), 1fr)); gap: 0 var(--itsm-space-4); }
.notification-policy-grid .filter-row .el-input-number { width: 100px; }
</style>
