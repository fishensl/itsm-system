<template>
  <div v-loading="loading" class="expand-detail">
    <template v-if="detail">
      <el-descriptions :column="3" border size="small">
        <el-descriptions-item label="客户">{{ detail.customer_name || '-' }}</el-descriptions-item>
        <el-descriptions-item label="故障时间">{{ detail.fault_time || '-' }}</el-descriptions-item>
        <el-descriptions-item label="处理人">{{ detail.handler || '-' }}</el-descriptions-item>
        <el-descriptions-item label="故障类型">{{ detail.fault_type || '-' }}</el-descriptions-item>
        <el-descriptions-item label="处理结果">
          <el-tag size="small" :type="FAULT_RESULT_TAG[detail.result] || 'danger'">
            {{ detail.result || '-' }}
          </el-tag>
        </el-descriptions-item>
        <el-descriptions-item label="恢复时间">{{ detail.recovery_time || '-' }}</el-descriptions-item>
      </el-descriptions>

      <el-divider content-position="left">故障描述</el-divider>
      <p class="detail-text">{{ detail.fault_description || '-' }}</p>

      <el-divider content-position="left">故障原因</el-divider>
      <p class="detail-text">{{ detail.fault_cause || '-' }}</p>

      <el-divider content-position="left">解决方案</el-divider>
      <p class="detail-text">{{ detail.solution || '-' }}</p>

      <el-divider content-position="left">影响范围</el-divider>
      <p class="detail-text">{{ detail.impact_range || '-' }}</p>

      <el-divider content-position="left">操作</el-divider>
      <div class="action-bar">
        <el-button v-if="user.hasPerm('fault:edit')" size="small" type="primary" plain
          @click="emit('edit')">编辑</el-button>
        <el-button v-if="user.hasPerm('fault:delete')" size="small" type="danger" plain
          @click="emit('delete')">删除</el-button>
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'
import { useUserStore } from '@/stores/user'
import { fetchFault, FAULT_RESULT_TAG, type Fault } from '@/api/faults'

const props = defineProps<{ row: Record<string, unknown> }>()
const emit = defineEmits<{ (e: 'edit'): void; (e: 'delete'): void }>()

const user = useUserStore()
const loading = ref(false)
const detail = ref<Fault | null>(null)

async function load() {
  loading.value = true
  try {
    detail.value = await fetchFault(props.row.id as number)
  } catch { /* toast */ } finally {
    loading.value = false
  }
}

// 列表刷新后行对象被替换 → 自动重取详情保持新鲜
watch(() => props.row, () => { load() })

load()
</script>

<style scoped>
.expand-detail { padding: 4px 8px 8px; }
.detail-text { white-space: pre-wrap; word-break: break-all; font-size: 13px; margin: 0; }
.action-bar { display: flex; gap: 8px; flex-wrap: wrap; align-items: center; }
</style>
