<template>
  <div v-loading="loading" class="expand-detail">
    <template v-if="detail">
      <el-descriptions :column="cols" border size="small">
        <el-descriptions-item :label="label('customer_name', '客户')">{{ detail.customer_name || '-' }}</el-descriptions-item>
        <el-descriptions-item :label="label('fault_time', '故障时间')">{{ detail.fault_time || '-' }}</el-descriptions-item>
        <el-descriptions-item :label="label('handler', '处理人')">{{ detail.handler || '-' }}</el-descriptions-item>
        <el-descriptions-item :label="label('fault_category', '故障分类')">{{ detail.fault_category || detail.fault_type || '-' }}</el-descriptions-item>
        <el-descriptions-item :label="label('result', '处理结果')">
          <el-tag size="small" :type="FAULT_RESULT_TAG[detail.result] || 'danger'">
            {{ detail.result || '-' }}
          </el-tag>
        </el-descriptions-item>
        <el-descriptions-item :label="label('recovery_time', '恢复时间')">{{ detail.recovery_time || '-' }}</el-descriptions-item>
      </el-descriptions>

      <el-divider content-position="left">处置时间</el-divider>
      <el-descriptions :column="cols" border size="small">
        <el-descriptions-item :label="label('handling_started_at', '处置开始')">
          {{ detail.timing?.started_at || '-' }}
        </el-descriptions-item>
        <el-descriptions-item :label="label('recovery_time', '处置结束')">
          {{ detail.timing?.finished_at || '-' }}
        </el-descriptions-item>
        <el-descriptions-item :label="label('handling_duration', '处置时效')">
          <span class="timing-primary">{{ detail.timing?.handling_duration_text || '-' }}</span>
          <span v-if="detail.timing?.active" class="timing-note">（截至当前）</span>
        </el-descriptions-item>
        <el-descriptions-item :label="label('handling_person_days', '实际人天')">
          {{ detail.timing ? `${detail.timing.handling_person_days} 人天` : '-' }}
        </el-descriptions-item>
        <el-descriptions-item :label="label('timing_source', '计时来源')">
          <router-link v-if="detail.timing?.source === 'ticket' && detail.ticket_id"
            :to="`/tickets/${detail.ticket_id}`" class="row-link">
            来自工单 {{ detail.ticket_number || `#${detail.ticket_id}` }}
          </router-link>
          <span v-else>{{ timingSourceLabel(detail.timing?.source) }}</span>
          <el-tag v-if="detail.timing?.is_estimated" size="small" type="warning" class="timing-tag">估算</el-tag>
        </el-descriptions-item>
        <el-descriptions-item label="计时周期">第 {{ detail.timing?.cycle_no || 1 }} 轮</el-descriptions-item>
      </el-descriptions>
      <p v-if="detail.timing?.is_estimated && detail.timing.estimate_reason" class="timing-warning">
        {{ detail.timing.estimate_reason }}
      </p>

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
import { ref, watch, computed } from 'vue'
import { useMobile } from '@/utils/useMobile'
import { useUserStore } from '@/stores/user'
import { fetchFault, FAULT_RESULT_TAG, type Fault } from '@/api/faults'
import { entityFieldLabel, fetchEntityMeta, type EntityMeta } from '@/api/meta'

const { isMobile } = useMobile()
// 移动端降为 2 列，避免每项过窄
const cols = computed(() => (isMobile.value ? 2 : 2))

const props = defineProps<{ row: Record<string, unknown> }>()
const emit = defineEmits<{ (e: 'edit'): void; (e: 'delete'): void }>()

const user = useUserStore()
const loading = ref(false)
const detail = ref<Fault | null>(null)
const metadata = ref<EntityMeta>()
const label = (key: string, fallback: string) => entityFieldLabel(metadata.value, key, fallback)
const timingSourceLabel = (source?: string) => ({
  manual: '手工记录', estimated: '历史估算', unknown: '暂无数据',
}[source || ''] || source || '-')

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
fetchEntityMeta('fault').then((meta) => { metadata.value = meta })
</script>

<style scoped>
.expand-detail { padding: 4px 8px 8px; }
.detail-text { white-space: pre-wrap; word-break: break-all; font-size: 13px; margin: 0; }
.action-bar { display: flex; gap: 8px; flex-wrap: wrap; align-items: center; }
.timing-primary { color: var(--el-color-primary); font-weight: 600; }
.timing-note { color: var(--itsm-text-muted); font-size: 12px; }
.timing-tag { margin-left: 6px; }
.timing-warning { color: var(--el-color-warning); font-size: 12px; margin: 8px 0 0; }
.row-link { color: var(--el-color-primary); text-decoration: none; font-weight: 500; }
</style>
