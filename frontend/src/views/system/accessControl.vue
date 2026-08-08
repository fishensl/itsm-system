<template>
  <div class="page-container">
    <div class="page-header">
      <h2 class="page-title">访问控制</h2>
    </div>

    <el-card shadow="never">
      <template #header>
        <div class="card-header">
          <span>内网 / VPN 可信网段</span>
          <el-tag :type="cfg.enabled ? 'success' : 'info'" size="small">
            {{ cfg.enabled ? '访问隔离已启用' : '未配置（全部视为内网）' }}
          </el-tag>
        </div>
      </template>

      <el-alert type="info" :closable="false" class="mb-2"
        title="外网仅可访问工单/故障处置流程；客户/设备/合同/销售/备件等敏感模块严格限内网/VPN。每行一个网段（IP 或 CIDR，如 192.168.0.0/16、172.16.5.0/24）。留空 = 不启用隔离（所有请求视为内网）。" />

      <el-input v-model="networksText" type="textarea" :rows="8"
        placeholder="192.168.0.0/16&#10;10.0.0.0/8&#10;172.16.5.0/24" />

      <div class="actions">
        <el-button type="primary" :loading="saving" @click="save">保存（即时生效）</el-button>
      </div>

      <el-divider content-position="left">当前生效网段（含默认回环/私网兜底）</el-divider>
      <div class="net-preview">
        <el-tag v-for="n in effectiveNets" :key="n" size="small" class="net-tag">{{ n }}</el-tag>
      </div>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useUiStore } from '@/stores/ui'
import { fetchAccessControl, saveAccessControl } from '@/api/system'

const ui = useUiStore()
const cfg = ref({ trusted_networks: [] as string[], enabled: false })
const networksText = ref('')
const saving = ref(false)

const DEFAULT_NETS = ['127.0.0.1', '::1', '10.0.0.0/8', '172.16.0.0/12', '192.168.0.0/16']
const effectiveNets = computed(() => {
  const lines = networksText.value.split('\n').map((s) => s.trim()).filter(Boolean)
  return Array.from(new Set([...DEFAULT_NETS, ...lines]))
})

onMounted(async () => {
  try {
    cfg.value = await fetchAccessControl()
    networksText.value = cfg.value.trusted_networks.join('\n')
  } catch { /* toast by interceptor */ }
})

async function save() {
  saving.value = true
  try {
    const nets = networksText.value.split('\n').map((s) => s.trim()).filter(Boolean)
    cfg.value = await saveAccessControl(nets)
    networksText.value = cfg.value.trusted_networks.join('\n')
    ui.toast('访问控制已保存（即时生效）', 'success')
  } catch (e) {
    ui.toast((e as Error).message, 'error')
  } finally {
    saving.value = false
  }
}
</script>

<style scoped>
.card-header { display: flex; justify-content: space-between; align-items: center; }
.mb-2 { margin-bottom: 12px; }
.actions { margin-top: 12px; }
.net-preview { display: flex; flex-wrap: wrap; gap: 6px; }
</style>
