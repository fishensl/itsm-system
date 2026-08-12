<template>
  <div class="page-container">
    <div class="page-header">
      <h2 class="page-title">AI 对接</h2>
      <div class="header-actions">
        <el-button v-if="user.hasPerm('ai:edit')" type="primary" :icon="Plus" @click="openCreate">
          新增配置
        </el-button>
      </div>
    </div>

    <el-alert type="info" :closable="false" class="ai-note" show-icon
      title="当前为 AI 配置管理：支持连通性测试，业务能力（巡检/故障智能分析）预留待启用" />

    <el-card v-loading="loading" shadow="never">
      <div class="cfg-grid">
        <div v-for="c in items" :key="c.id" class="cfg-card">
          <div class="cfg-head">
            <span class="cfg-provider">{{ c.provider }}</span>
            <el-tag size="small" :type="c.is_enabled ? 'success' : 'info'">
              {{ c.is_enabled ? '启用' : '停用' }}
            </el-tag>
          </div>
          <div class="cfg-model">{{ c.model_name || '-' }}</div>
          <div class="cfg-endpoint">{{ c.api_endpoint || '使用默认端点' }}</div>
          <div class="cfg-meta">
            <el-tag v-if="c.has_api_key" size="small" type="warning">已配置 Key</el-tag>
            <el-tag v-else size="small" type="info">未配置 Key</el-tag>
          </div>
          <div class="cfg-actions">
            <el-button v-if="user.hasPerm('ai:edit')" size="small" link type="primary" :loading="testingSet.has(c.id)"
              @click="onTest(c)">测试连接</el-button>
            <el-button v-if="user.hasPerm('ai:edit')" size="small" link type="primary" @click="openEdit(c)">编辑</el-button>
            <el-button v-if="user.hasPerm('ai:edit')" size="small" link type="danger" @click="onDelete(c)">删除</el-button>
          </div>
        </div>
      </div>
      <el-empty v-if="!loading && !items.length" description="暂无 AI 配置" :image-size="60" />
    </el-card>

    <!-- 新增/编辑 -->
    <el-dialog v-model="formVisible" :title="form.id ? '编辑 AI 配置' : '新增 AI 配置'" width="640px" destroy-on-close>
      <el-form ref="formRef" :model="form" label-width="120px">
        <el-form-item label="服务商">
          <el-select v-model="form.provider" style="width: 100%">
            <el-option v-for="p in ['OpenAI', 'Anthropic', 'Ollama', '自定义']" :key="p" :label="p" :value="p" />
          </el-select>
        </el-form-item>
        <el-form-item label="API 端点">
          <el-input v-model="form.api_endpoint" placeholder="留空使用默认端点" />
        </el-form-item>
        <el-form-item label="模型名称">
          <el-input v-model="form.model_name" placeholder="如 gpt-4" />
        </el-form-item>
        <el-form-item :label="form.has_api_key ? 'API 密钥（留空不修改）' : 'API 密钥'">
          <el-input v-model="form.api_key" type="password" show-password autocomplete="new-password" placeholder="API 密钥" />
        </el-form-item>
        <el-row :gutter="12">
          <el-col :span="12">
            <el-form-item label="最大 Token">
              <el-input-number v-model="form.max_tokens" :min="1" :max="128000" style="width: 100%" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="温度">
              <el-input-number v-model="form.temperature" :min="0" :max="2" :step="0.1" style="width: 100%" />
            </el-form-item>
          </el-col>
        </el-row>
        <el-form-item label="启用">
          <el-switch v-model="form.is_enabled" active-text="启用此配置" />
        </el-form-item>
        <el-form-item label="巡检分析提示词">
          <el-input v-model="form.inspection_prompt_template" type="textarea" :rows="3" />
        </el-form-item>
        <el-form-item label="故障分析提示词">
          <el-input v-model="form.fault_prompt_template" type="textarea" :rows="3" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="formVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="save">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ElMessageBox } from 'element-plus/es/components/message-box/index'
import { ref, reactive, onMounted } from 'vue'
import { Plus } from '@element-plus/icons-vue'
import {
  fetchAiConfigs, createAiConfig, updateAiConfig, deleteAiConfig, testAiConfig, type AiConfigItem,
} from '@/api/system'
import { useUserStore } from '@/stores/user'
import { useUiStore } from '@/stores/ui'

const user = useUserStore()
const ui = useUiStore()
const items = ref<AiConfigItem[]>([])
const loading = ref(false)
const testingSet = ref(new Set<number>())
const formVisible = ref(false)
const saving = ref(false)
const formRef = ref()
const form = reactive<Record<string, unknown>>({
  id: null, provider: 'OpenAI', api_endpoint: '', model_name: '', api_key: '',
  max_tokens: 2048, temperature: 0.7, is_enabled: false,
  inspection_prompt_template: '', fault_prompt_template: '', has_api_key: false,
})

function load() {
  loading.value = true
  fetchAiConfigs()
    .then((d) => { items.value = d })
    .catch(() => { /* toast */ })
    .finally(() => { loading.value = false })
}

function openCreate() {
  Object.assign(form, {
    id: null, provider: 'OpenAI', api_endpoint: '', model_name: '', api_key: '',
    max_tokens: 2048, temperature: 0.7, is_enabled: false,
    inspection_prompt_template: '', fault_prompt_template: '', has_api_key: false,
  })
  formVisible.value = true
}

function openEdit(row: AiConfigItem) {
  Object.assign(form, {
    id: row.id, provider: row.provider, api_endpoint: row.api_endpoint, model_name: row.model_name,
    api_key: '', max_tokens: row.max_tokens, temperature: row.temperature, is_enabled: row.is_enabled,
    inspection_prompt_template: row.inspection_prompt_template, fault_prompt_template: row.fault_prompt_template,
    has_api_key: row.has_api_key,
  })
  formVisible.value = true
}

async function save() {
  saving.value = true
  try {
    const payload = {
      provider: String(form.provider), api_endpoint: String(form.api_endpoint || ''),
      model_name: String(form.model_name || ''), api_key: String(form.api_key || ''),
      max_tokens: Number(form.max_tokens), temperature: Number(form.temperature),
      is_enabled: !!form.is_enabled, inspection_prompt_template: String(form.inspection_prompt_template || ''),
      fault_prompt_template: String(form.fault_prompt_template || ''),
    }
    if (form.id) {
      await updateAiConfig(form.id as number, payload)
      ui.toast('已保存', 'success')
    } else {
      await createAiConfig(payload)
      ui.toast('已添加', 'success')
    }
    formVisible.value = false
    load()
  } catch (e) {
    ui.toast((e as Error).message, 'error')
  } finally {
    saving.value = false
  }
}

async function onTest(row: AiConfigItem) {
  testingSet.value.add(row.id)
  try {
    const r = await testAiConfig(row.id)
    if (r.success) ui.toast('连接成功', 'success')
    else ui.toast(`连接失败：${r.message}`, 'error')
  } catch (e) {
    ui.toast((e as Error).message, 'error')
  } finally {
    testingSet.value.delete(row.id)
  }
}

async function onDelete(row: AiConfigItem) {
  try {
    await ElMessageBox.confirm(`确定删除 AI 配置「${row.provider} / ${row.model_name}」吗？`, '删除确认',
      { type: 'warning' })
  } catch { return }
  try {
    await deleteAiConfig(row.id)
    ui.toast('已删除', 'success')
    load()
  } catch (e) {
    ui.toast((e as Error).message, 'error')
  }
}

onMounted(load)
</script>

<style scoped>
.cfg-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 12px; }
.cfg-card {
  border: 1px solid var(--itsm-border); border-radius: 8px; padding: 14px;
  display: flex; flex-direction: column; gap: 6px;
}
.cfg-head { display: flex; align-items: center; justify-content: space-between; }
.cfg-provider { font-weight: 700; font-size: 15px; }
.cfg-model { font-size: 13px; }
.cfg-endpoint { font-size: 12px; color: var(--itsm-text-muted); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.cfg-meta { display: flex; gap: 4px; }
.cfg-actions { margin-top: auto; display: flex; gap: 4px; }
</style>
