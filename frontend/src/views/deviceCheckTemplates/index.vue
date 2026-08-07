<template>
  <div class="page-container">
    <div class="page-header">
      <h2 class="page-title">设备检查模板</h2>
      <div class="header-actions">
        <el-button v-if="user.hasPerm('inspection:edit')" type="primary" :icon="Plus" @click="openCreate">
          新增模板
        </el-button>
      </div>
    </div>

    <el-card v-loading="loading" shadow="never">
      <div v-for="cat in data?.category_order || []" :key="cat">
        <template v-if="(data?.groups[cat] || []).length">
          <div class="cat-title">{{ cat }}</div>
          <div class="cat-grid">
            <div v-for="t in data!.groups[cat]" :key="t.id" class="tpl-card"
              :class="{ 'tpl-expanded': expandedId === t.id }">
              <div class="tpl-name">
                {{ t.name }}
                <el-tag v-if="!t.is_active" size="small" type="info">停用</el-tag>
              </div>
              <div class="tpl-sub">{{ t.device_sub_type || '无细分类别' }}</div>
              <div class="tpl-meta">
                <span>{{ t.total_sub_items }} 个检查点</span>
              </div>
              <div class="tpl-actions">
                <el-button size="small" link type="primary" @click="toggleDetail(t)">
                  {{ expandedId === t.id ? '收起' : '查看' }}
                </el-button>
                <el-button v-if="user.hasPerm('inspection:edit')" size="small" link type="primary"
                  @click="openEdit(t)">编辑</el-button>
                <el-button v-if="user.hasPerm('inspection:delete')" size="small" link type="danger"
                  @click="onDelete(t)">删除</el-button>
              </div>

              <!-- 卡片内展开详情 -->
              <div v-if="expandedId === t.id" class="tpl-detail">
                <el-descriptions :column="2" border size="small">
                  <el-descriptions-item label="设备类别">{{ t.device_category || '-' }}</el-descriptions-item>
                  <el-descriptions-item label="细分类别">{{ t.device_sub_type || '-' }}</el-descriptions-item>
                  <el-descriptions-item label="状态">
                    <el-tag size="small" :type="t.is_active ? 'success' : 'info'">
                      {{ t.is_active ? '启用' : '停用' }}
                    </el-tag>
                  </el-descriptions-item>
                  <el-descriptions-item label="检查点">{{ t.total_sub_items }}</el-descriptions-item>
                </el-descriptions>
                <el-divider content-position="left">检查项</el-divider>
                <div v-for="(it, i) in t.items" :key="i" class="item-block">
                  <div class="item-title">
                    {{ i + 1 }}. {{ it.name }}
                    <el-tag v-if="!it.enabled" size="small" type="info">停用</el-tag>
                  </div>
                  <div v-if="it.description" class="item-desc">{{ it.description }}</div>
                  <div v-if="it.sub_items?.length" class="sub-list">
                    <div v-for="(s, j) in it.sub_items" :key="j" class="sub-item">
                      {{ s.label || '主项' }}（{{ fieldTypeLabel(s.field_type) }}）
                      <el-tag v-if="s.required" size="small" type="danger" class="ml-1">必填</el-tag>
                    </div>
                  </div>
                </div>
                <el-empty v-if="!t.items?.length" description="无检查项" :image-size="50" />
              </div>
            </div>
          </div>
        </template>
      </div>
      <el-empty v-if="!loading && !Object.keys(data?.groups || {}).length" description="暂无设备检查模板"
        :image-size="60" />
    </el-card>

    <!-- 新增/编辑 -->
    <el-dialog v-model="formVisible" :title="form.id ? '编辑设备检查模板' : '新增设备检查模板'" width="760px" destroy-on-close>
      <el-form ref="formRef" :model="form" label-width="110px">
        <el-form-item label="模板名称" prop="name" :rules="[{ required: true, message: '请输入名称', trigger: 'blur' }]">
          <el-input v-model="form.name" placeholder="如：华为 S5735 巡检检查项" />
        </el-form-item>
        <el-row :gutter="12">
          <el-col :span="12">
            <el-form-item label="设备类别">
              <el-select v-model="form.device_category" style="width: 100%">
                <el-option v-for="c in data?.category_order || []" :key="c" :label="c" :value="c" />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="细分类别">
              <el-input v-model="form.device_sub_type" placeholder="如：核心交换机（可选）" />
            </el-form-item>
          </el-col>
        </el-row>
        <el-form-item label="状态">
          <el-switch v-model="form.is_active" active-text="启用" />
        </el-form-item>

        <el-form-item label="检查项">
          <div class="items-editor">
            <div v-for="(it, i) in (form.items as CheckItem[])" :key="i" class="item-row">
              <div class="item-row-head">
                <span class="item-no">{{ i + 1 }}</span>
                <el-input v-model="it.name" placeholder="检查项名称" class="item-name" />
                <el-button size="small" link type="danger" :icon="Delete" @click="removeItem(i)" />
              </div>
              <el-input v-model="it.description" placeholder="检查项说明（可选）" class="item-desc-input" />
            </div>
            <el-button size="small" plain :icon="Plus" @click="addItem">添加检查项</el-button>
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
  </div>
</template>

<script setup lang="ts">
import { ElMessageBox } from 'element-plus/es/components/message-box/index'
import { ref, reactive, onMounted } from 'vue'
import { Plus, Delete } from '@element-plus/icons-vue'
import {
  fetchDeviceCheckTemplates, createDeviceCheckTemplate, updateDeviceCheckTemplate, deleteDeviceCheckTemplate,
  type DeviceCheckTemplateListData, type DeviceCheckTemplateItem, type CheckItem,
} from '@/api/templates'
import { useUserStore } from '@/stores/user'
import { useUiStore } from '@/stores/ui'

const user = useUserStore()
const ui = useUiStore()
const data = ref<DeviceCheckTemplateListData | null>(null)
const loading = ref(false)
const formVisible = ref(false)
const saving = ref(false)
const formRef = ref()
const expandedId = ref<number | null>(null)
const form = reactive<Record<string, unknown>>({
  id: null, name: '', device_category: '网络设备', device_sub_type: '', items: [], is_active: true, remark: '',
})

const FIELD_TYPES: Record<string, string> = {
  status_note: '状态备注', percentage: '百分比', ping_test: 'Ping 测试', status_abnormal: '异常状态',
  text: '文本', multiline_text: '多行文本', number: '数字', dropdown: '下拉', image: '照片',
  date: '日期', version_check: '版本核对',
}

function fieldTypeLabel(t?: string) {
  return (t && FIELD_TYPES[t]) || t || '文本'
}

function load() {
  loading.value = true
  fetchDeviceCheckTemplates()
    .then((d) => { data.value = d })
    .catch(() => { /* toast */ })
    .finally(() => { loading.value = false })
}

function openCreate() {
  Object.assign(form, {
    id: null, name: '', device_category: '网络设备', device_sub_type: '', items: [], is_active: true, remark: '',
  })
  formVisible.value = true
}

function openEdit(row: DeviceCheckTemplateItem) {
  Object.assign(form, {
    id: row.id, name: row.name, device_category: row.device_category, device_sub_type: row.device_sub_type,
    items: JSON.parse(JSON.stringify(row.items || [])), is_active: row.is_active, remark: row.remark,
  })
  formVisible.value = true
}

function toggleDetail(row: DeviceCheckTemplateItem) {
  expandedId.value = expandedId.value === row.id ? null : row.id
}

function addItem() {
  const items = form.items as Array<Record<string, unknown>>
  items.push({ name: '', description: '', enabled: true })
  form.items = [...items]
}

function removeItem(i: number) {
  const items = form.items as Array<Record<string, unknown>>
  items.splice(i, 1)
  form.items = [...items]
}

async function save() {
  try { await formRef.value?.validate() } catch { return }
  saving.value = true
  try {
    const payload = { ...form }
    delete payload.id
    if (form.id) {
      await updateDeviceCheckTemplate(form.id as number, payload)
      ui.toast('已保存', 'success')
    } else {
      await createDeviceCheckTemplate(payload)
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

async function onDelete(row: DeviceCheckTemplateItem) {
  try {
    await ElMessageBox.confirm(`确定删除模板「${row.name}」吗？`, '删除确认', { type: 'warning' })
  } catch { return }
  try {
    await deleteDeviceCheckTemplate(row.id)
    ui.toast('已删除', 'success')
    load()
  } catch (e) {
    ui.toast((e as Error).message, 'error')
  }
}

onMounted(load)
</script>

<style scoped>
.cat-title { font-size: 14px; font-weight: 700; margin: 14px 0 8px; }
.cat-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(220px, 1fr)); gap: 10px; }
.tpl-card {
  border: 1px solid var(--itsm-border); border-radius: 8px; padding: 12px;
  display: flex; flex-direction: column; gap: 4px;
}
.tpl-name { font-weight: 600; display: flex; align-items: center; gap: 6px; }
.tpl-sub { font-size: 12px; color: var(--itsm-text-muted); }
.tpl-meta { font-size: 12px; color: var(--itsm-text-muted); }
.tpl-actions { margin-top: auto; display: flex; gap: 4px; }
.tpl-expanded { border-color: var(--el-color-primary); }
.tpl-detail { margin-top: 10px; padding-top: 10px; border-top: 1px dashed var(--itsm-border); }
.item-block { border: 1px solid var(--itsm-border); border-radius: 8px; padding: 10px; margin-bottom: 8px; }
.item-title { font-weight: 600; display: flex; align-items: center; gap: 8px; }
.item-desc { font-size: 12px; color: var(--itsm-text-muted); margin: 4px 0; }
.sub-list { display: flex; flex-direction: column; gap: 3px; margin-top: 4px; }
.sub-item { font-size: 12px; display: flex; align-items: center; gap: 4px; }
.ml-1 { margin-left: 4px; }
.items-editor { width: 100%; display: flex; flex-direction: column; gap: 8px; }
.item-row { border: 1px solid var(--itsm-border); border-radius: 8px; padding: 8px; }
.item-row-head { display: flex; align-items: center; gap: 8px; }
.item-no { font-weight: 600; color: var(--itsm-text-muted); }
.item-name { flex: 1; }
.item-desc-input { margin-top: 6px; }
</style>
