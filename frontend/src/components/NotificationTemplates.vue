<template>
  <el-collapse><el-collapse-item title="客户消息模板（全局）">
    <p>主题由系统单独显示，正文每行一项；无需再次添加主题。仅支持 {title}、{content}，版本发布只影响新事件。</p>
    <el-select v-model="selected" @change="select"><el-option v-for="t in items" :key="t.event_type" :value="t.event_type" :label="t.label" /></el-select>
    <el-input v-model="body" type="textarea" :rows="4" maxlength="1200" show-word-limit />
    <p>示例预览（不发送）：</p><pre class="notification-content">{{ preview }}</pre>
    <el-button type="primary" @click="save">发布新版本</el-button>
  </el-collapse-item></el-collapse>
</template>
<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { ElMessageBox, ElMessage } from 'element-plus'
import request from '@/utils/request'
type Template = { event_type: string; label: string; body: string; version: number }
const items = ref<Template[]>([]), selected = ref(''), body = ref('{content}')
const sampleTitle = '示例客户2026年第三季度巡检'
const sampleContent = '计划时间：2026-09-07 至 2026-09-11\n巡检地点：示例客户\n巡检工程师：示例工程师\n任务状态：已完成\n实施开始：2026-09-08 08:30\n实施结束：2026-09-08 17:30\n累计耗时：7小时30分钟\n累计人天：0.94 人天'
const preview = computed(() => [sampleTitle, ...Array.from(new Set(body.value.split('{title}').join(sampleTitle).split('{content}').join(sampleContent).split('\n').map(s => s.trim()).filter(s => s && s !== sampleTitle)))].join('\n'))
function select() { body.value = items.value.find(t => t.event_type === selected.value)?.body || '{content}' }
async function load() { items.value = (await request<{ items: Template[] }>({ url: '/api/notify-templates' })).items; selected.value ||= items.value[0]?.event_type || ''; select() }
async function save() { await ElMessageBox.confirm('该模板影响所有客户的新事件，确认发布？', '发布模板'); await request({ url: `/api/notify-templates/${selected.value}`, method: 'PUT', data: { body: body.value } }); await load(); ElMessage.success('已发布新版本') }
onMounted(load)
</script>
