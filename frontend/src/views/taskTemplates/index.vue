<template>
  <div class="page-container">
    <div class="page-header">
      <h2 class="page-title">任务模板</h2>
      <div class="header-actions">
        <el-button v-if="user.hasPerm('inspection:edit')" type="primary" :icon="Plus" @click="openCreate">
          新增模板
        </el-button>
      </div>
    </div>

    <el-card shadow="never">
      <el-table v-loading="loading" :data="data?.templates || []" border row-key="id">
        <el-table-column prop="name" label="模板名称" min-width="180" />
        <el-table-column prop="category" label="类别" width="100">
          <template #default="{ row }"><el-tag size="small">{{ row.category || '-' }}</el-tag></template>
        </el-table-column>
        <el-table-column prop="inspection_type" label="巡检类型" width="120" />
        <el-table-column prop="frequency" label="推荐频率" width="90">
          <template #default="{ row }">{{ row.frequency || '-' }}</template>
        </el-table-column>
        <el-table-column label="适用级别" width="100">
          <template #default="{ row }">{{ row.customer_tier === 'all' ? '全部' : (row.customer_tier || '-') }}</template>
        </el-table-column>
        <el-table-column label="关联设备模板" min-width="160">
          <template #default="{ row }">
            <el-tag v-for="dt in deviceTemplateNames(row.device_template_ids)" :key="dt.id" size="small"
              class="dt-tag">{{ dt.name }}</el-tag>
            <span v-if="!row.device_template_ids?.length" class="muted">-</span>
          </template>
        </el-table-column>
        <el-table-column prop="is_active" label="状态" width="80">
          <template #default="{ row }">
            <el-tag size="small" :type="row.is_active ? 'success' : 'info'">{{ row.is_active ? '启用' : '停用' }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column v-if="user.hasPerm('inspection:edit')" label="操作" width="150" fixed="right">
          <template #default="{ row }">
            <el-button size="small" link type="primary" @click="openEdit(row)">编辑</el-button>
            <el-button v-if="user.hasPerm('inspection:delete')" size="small" link type="danger"
              @click="onDelete(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
      <el-empty v-if="!loading && !data?.templates?.length" description="暂无任务模板" :image-size="60" />
    </el-card>

    <!-- 新增/编辑 -->
    <el-dialog v-model="formVisible" :title="form.id ? '编辑任务模板' : '新增任务模板'" width="720px" destroy-on-close>
      <el-form ref="formRef" :model="form" label-width="110px">
        <el-form-item label="模板名称" prop="name" :rules="[{ required: true, message: '请输入名称', trigger: 'blur' }]">
          <el-input v-model="form.name" placeholder="如：季度巡检任务模板" />
        </el-form-item>
        <el-row :gutter="12">
          <el-col :span="12">
            <el-form-item label="类别">
              <el-select v-model="form.category" style="width: 100%">
                <el-option v-for="c in ['日常巡检', '季度巡检', '年度巡检', '应急巡检']" :key="c" :label="c" :value="c" />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="巡检类型">
              <el-select v-model="form.inspection_type" style="width: 100%">
                <el-option v-for="t in ['月度巡检', '季度巡检', '攻防演练专项', '漏洞扫描专项']" :key="t" :label="t" :value="t" />
              </el-select>
            </el-form-item>
          </el-col>
        </el-row>
        <el-row :gutter="12">
          <el-col :span="12">
            <el-form-item label="推荐频率">
              <el-select v-model="form.frequency" clearable style="width: 100%">
                <el-option v-for="f in ['每月', '每季度', '每半年', '每年']" :key="f" :label="f" :value="f" />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="适用客户级别">
              <el-select v-model="form.customer_tier" style="width: 100%">
                <el-option v-for="t in [{ v: 'all', l: '全部' }, { v: '核心', l: '核心' }, { v: '重点', l: '重点' }, { v: '常规', l: '常规' }]"
                  :key="t.v" :label="t.l" :value="t.v" />
              </el-select>
            </el-form-item>
          </el-col>
        </el-row>

        <el-form-item label="章节配置">
          <div class="sections-editor">
            <div v-for="(s, i) in (form.sections as TaskTemplateSection[])" :key="i" class="section-row">
              <el-input v-model="s.title" placeholder="章节标题" class="section-title" />
              <el-switch v-model="s.enabled" active-text="启用" />
              <el-button size="small" link type="danger" :icon="Delete" @click="removeSection(i)" />
            </div>
            <el-button size="small" plain :icon="Plus" @click="addSection">添加章节</el-button>
          </div>
        </el-form-item>

        <el-form-item label="关联设备模板">
          <div class="dt-select">
            <el-select v-model="form.device_template_ids" multiple filterable placeholder="选择设备检查模板（按选择顺序）"
              style="width: 100%">
              <el-option
                v-for="dt in data?.device_templates || []"
                :key="dt.id"
                :label="`${dt.name}（${dt.device_category || '-'}${dt.device_sub_type ? ' / ' + dt.device_sub_type : ''}）`"
                :value="dt.id"
              />
            </el-select>
            <el-button size="small" plain class="mt-1" @click="openMatcher">按客户设备自动匹配</el-button>
          </div>
        </el-form-item>
        <el-form-item label="必传资料">
          <div class="required-editor">
            <div v-for="item in REQUIRED_ASSET_ITEMS" :key="item.key" class="required-row">
              <el-switch v-model="(form.required_assets as Record<string, boolean>)[item.key]" />
              <span class="required-label">{{ item.label }}</span>
              <span class="required-desc">{{ item.desc }}</span>
            </div>
            <div class="form-text text-muted small">
              工程师提交审核时，必传项必须上传或填写无法上传的原因；未开启的项可选提交
            </div>
          </div>
        </el-form-item>

        <el-form-item label="备注">
          <el-input v-model="form.remark" type="textarea" :rows="2" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="formVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="save">保存</el-button>
      </template>
    </el-dialog>

    <!-- 自动匹配 -->
    <el-dialog v-model="matchVisible" title="按客户设备自动匹配设备模板" width="720px">
      <el-form label-width="90px">
        <el-form-item label="选择客户">
          <el-select v-model="matchCustomerId" filterable placeholder="选择客户" style="width: 100%">
            <el-option v-for="c in data?.customers || []" :key="c.id" :label="c.name" :value="c.id" />
          </el-select>
        </el-form-item>
      </el-form>
      <el-button type="primary" plain :loading="matching" :disabled="!matchCustomerId" @click="doMatch">匹配</el-button>
      <div v-if="matchData" class="match-result">
        <div v-for="g in matchData.groups" :key="g.device_category" class="match-group">
          <div class="match-group-title">
            {{ g.device_category }} <el-tag size="small" type="info">{{ g.devices_count }} 台</el-tag>
          </div>
          <div v-for="tpl in g.matched_templates" :key="tpl.id" class="match-item">
            <el-checkbox
              :model-value="(form.device_template_ids as number[]).includes(tpl.id)"
              @change="(v: boolean | string | number) => toggleMatch(tpl.id, !!v)"
            >
              {{ tpl.name }}
              <span class="muted">（{{ tpl.match_score === 100 ? '精确' : '近似' }} · {{ tpl.items_count }} 检查点）</span>
            </el-checkbox>
          </div>
          <div v-if="!g.matched_templates.length" class="muted">无匹配模板</div>
        </div>
      </div>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ElMessageBox } from 'element-plus/es/components/message-box/index'
import { ref, reactive, onMounted } from 'vue'
import { Plus, Delete } from '@element-plus/icons-vue'
import {
  fetchTaskTemplates, createTaskTemplate, updateTaskTemplate, deleteTaskTemplate, matchDeviceTemplates,
  type TaskTemplateListData, type TaskTemplateItem, type TaskTemplateSection, type MatchGroup, type DeviceTemplateRef,
} from '@/api/templates'
import { useUserStore } from '@/stores/user'
import { useUiStore } from '@/stores/ui'

const user = useUserStore()
const ui = useUiStore()
const data = ref<TaskTemplateListData | null>(null)
const loading = ref(false)
const formVisible = ref(false)
const saving = ref(false)
const formRef = ref()
const form = reactive<Record<string, unknown>>({
  id: null, name: '', category: '日常巡检', inspection_type: '月度巡检', frequency: '',
  customer_tier: 'all', sections: [], device_template_ids: [], remark: '',
  required_assets: { report: true, config_zip: false, config_text: false, topology: false, asset_list: false },
})

const REQUIRED_ASSET_ITEMS = [
  { key: 'report', label: '巡检报告', desc: '巡检结果报告文件' },
  { key: 'config_zip', label: '完整配置备份包', desc: '巡检备份配置压缩包' },
  { key: 'config_text', label: '核心设备文本配置', desc: '核心交换机/路由器文本配置文件' },
  { key: 'topology', label: '拓扑图', desc: '现场拓扑图（同步设备管理拓扑）' },
  { key: 'asset_list', label: '资产清单', desc: '设备资产清单 Excel（解析导入设备）' },
]

const matchVisible = ref(false)
const matchCustomerId = ref<number | null>(null)
const matching = ref(false)
const matchData = ref<{ groups: MatchGroup[]; total_devices: number } | null>(null)

function load() {
  loading.value = true
  fetchTaskTemplates()
    .then((d) => { data.value = d })
    .catch(() => { /* toast */ })
    .finally(() => { loading.value = false })
}

function deviceTemplateNames(ids: number[]) {
  const map = new Map((data.value?.device_templates || []).map((d) => [d.id, d]))
  return (ids || [])
    .map((id) => map.get(id))
    .filter((d): d is DeviceTemplateRef => !!d)
}

function openCreate() {
  Object.assign(form, {
    id: null, name: '', category: '日常巡检', inspection_type: '月度巡检', frequency: '',
    customer_tier: 'all', sections: [], device_template_ids: [], remark: '',
    required_assets: { report: true, config_zip: false, config_text: false, topology: false, asset_list: false },
  })
  formVisible.value = true
}

function openEdit(row: TaskTemplateItem) {
  Object.assign(form, {
    id: row.id, name: row.name, category: row.category, inspection_type: row.inspection_type,
    frequency: row.frequency, customer_tier: row.customer_tier,
    sections: (row.sections || []).map((s) => ({ ...s })),
    device_template_ids: [...(row.device_template_ids || [])],
    remark: row.remark, is_active: row.is_active,
    required_assets: { report: true, config_zip: false, config_text: false, topology: false, asset_list: false,
      ...(row.required_assets || {}) },
  })
  formVisible.value = true
}

function addSection() {
  const sections = form.sections as Array<Record<string, unknown>>
  sections.push({ key: `s${Date.now()}`, title: '', enabled: true })
  form.sections = [...sections]
}

function removeSection(i: number) {
  const sections = form.sections as Array<Record<string, unknown>>
  sections.splice(i, 1)
  form.sections = [...sections]
}

function openMatcher() {
  matchVisible.value = true
  matchData.value = null
}

async function doMatch() {
  if (!matchCustomerId.value) return
  matching.value = true
  try {
    matchData.value = await matchDeviceTemplates(matchCustomerId.value)
  } catch (e) {
    ui.toast((e as Error).message, 'error')
  } finally {
    matching.value = false
  }
}

function toggleMatch(tplId: number, on: boolean) {
  const ids = new Set(form.device_template_ids as number[])
  if (on) ids.add(tplId)
  else ids.delete(tplId)
  form.device_template_ids = [...ids]
}

async function save() {
  try { await formRef.value?.validate() } catch { return }
  saving.value = true
  try {
    const payload = { ...form }
    delete payload.id
    if (form.id) {
      await updateTaskTemplate(form.id as number, payload)
      ui.toast('已保存', 'success')
    } else {
      await createTaskTemplate(payload)
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

async function onDelete(row: TaskTemplateItem) {
  try {
    await ElMessageBox.confirm(`确定删除模板「${row.name}」吗？`, '删除确认', { type: 'warning' })
  } catch { return }
  try {
    await deleteTaskTemplate(row.id)
    ui.toast('已删除', 'success')
    load()
  } catch (e) {
    ui.toast((e as Error).message, 'error')
  }
}

onMounted(load)
</script>

<style scoped>
.dt-tag { margin-right: 4px; margin-bottom: 2px; }
.muted { color: var(--itsm-text-muted); font-size: 12px; }
.sections-editor { width: 100%; display: flex; flex-direction: column; gap: 6px; }
.section-row { display: flex; align-items: center; gap: 8px; }
.section-title { flex: 1; }
.required-editor { width: 100%; display: flex; flex-direction: column; gap: 8px; }
.required-row { display: flex; align-items: center; gap: 10px; }
.required-label { font-size: 13px; font-weight: 600; width: 130px; }
.required-desc { font-size: 12px; color: var(--itsm-text-muted); }
.mt-1 { margin-top: 6px; }
.match-result { margin-top: 12px; }
.match-group { border: 1px solid var(--itsm-border); border-radius: 8px; padding: 10px; margin-bottom: 8px; }
.match-group-title { font-weight: 600; margin-bottom: 6px; display: flex; align-items: center; gap: 8px; }
.match-item { padding: 3px 0; }
</style>
