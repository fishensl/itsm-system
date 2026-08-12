<template>
  <div>
    <div class="tab-toolbar">
      <el-button v-if="user.hasPerm('device:edit')" type="primary" :icon="Plus" @click="openCreate">
        新增
      </el-button>
    </div>

    <el-table v-loading="loading" :data="items" border size="small" row-key="id">
      <el-table-column prop="name" :label="label('name', '名称')" min-width="200" />
      <el-table-column v-if="showType" prop="field_type" :label="label('field_type', '字段类型')" width="120">
        <template #default="{ row }">
          <el-tag size="small" :type="row.field_type === 'date' ? 'warning' : 'info'">
            {{ FIELD_TYPE_LABELS[row.field_type] || FIELD_TYPE_LABELS.text }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="sort_order" :label="label('sort_order', '排序')" width="80" />
      <el-table-column v-if="user.hasPerm('device:edit')" label="操作" width="150" fixed="right">
        <template #default="{ row }">
          <el-button size="small" link type="primary" @click="openEdit(row)">编辑</el-button>
          <el-button v-if="user.hasPerm('device:delete')" size="small" link type="danger" @click="onDelete(row)">
            删除
          </el-button>
        </template>
      </el-table-column>
    </el-table>
    <el-empty v-if="!loading && !items.length" description="暂无数据" :image-size="50" />

    <el-dialog v-model="formVisible" :title="form.id ? '编辑' : '新增'" width="420px" destroy-on-close>
      <el-form ref="formRef" :model="form" label-width="80px">
        <el-form-item :label="label('name', '名称', 'form')" prop="name" :rules="[{ required: true, message: '请输入名称', trigger: 'blur' }]">
          <el-input v-model="form.name" placeholder="名称" />
        </el-form-item>
        <el-form-item v-if="showType" :label="label('field_type', '字段类型', 'form')">
          <el-select v-model="form.field_type" style="width: 100%">
            <el-option v-for="(optionLabel, value) in FIELD_TYPE_OPTIONS" :key="value"
              :label="optionLabel" :value="value" />
          </el-select>
        </el-form-item>
        <el-form-item :label="label('sort_order', '排序', 'form')">
          <el-input-number v-model="form.sort_order" :min="0" />
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
  fetchDeviceDict, createDeviceDict, updateDeviceDict, deleteDeviceDict, type DictItem,
} from '@/api/deviceDicts'
import { useUserStore } from '@/stores/user'
import { useUiStore } from '@/stores/ui'
import { entityFieldLabel, fetchEntityMeta, type EntityMeta } from '@/api/meta'

const props = defineProps<{ resource: 'types' | 'brands' | 'network-types' | 'custom-fields'; showType: boolean }>()

/** 自定义字段类型（对齐后端 utils/permission.py FIELD_TYPE_CHOICES） */
const FIELD_TYPE_OPTIONS: Record<string, string> = {
  text: '单行文本',
  multiline_text: '多行文本',
  dropdown: '下拉选择',
  number: '数字',
  image: '图片上传',
  date: '日期',
}
const FIELD_TYPE_LABELS = FIELD_TYPE_OPTIONS

const user = useUserStore()
const ui = useUiStore()
const items = ref<DictItem[]>([])
const metadata = ref<EntityMeta>()
const loading = ref(false)
const formVisible = ref(false)
const saving = ref(false)
const formRef = ref()
const form = reactive<Record<string, unknown>>({ id: null, name: '', sort_order: 0, field_type: 'text' })

function label(key: string, fallback: string, profile = 'list') {
  return entityFieldLabel(metadata.value, key, fallback, profile)
}

function load() {
  loading.value = true
  fetchDeviceDict(props.resource)
    .then((d) => { items.value = d })
    .catch(() => { /* toast */ })
    .finally(() => { loading.value = false })
}

function openCreate() {
  Object.assign(form, { id: null, name: '', sort_order: 0, field_type: 'text' })
  formVisible.value = true
}

function openEdit(row: DictItem) {
  Object.assign(form, { id: row.id, name: row.name, sort_order: row.sort_order, field_type: row.field_type || 'text' })
  formVisible.value = true
}

async function save() {
  try { await formRef.value?.validate() } catch { return }
  saving.value = true
  try {
    const payload = { name: String(form.name), sort_order: Number(form.sort_order || 0) }
    if (props.showType) Object.assign(payload, { field_type: String(form.field_type || 'text') })
    if (form.id) {
      await updateDeviceDict(props.resource, form.id as number, payload)
      ui.toast('已保存', 'success')
    } else {
      await createDeviceDict(props.resource, payload)
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

async function onDelete(row: DictItem) {
  try {
    await ElMessageBox.confirm(`确定删除「${row.name}」吗？`, '删除确认', { type: 'warning' })
  } catch { return }
  try {
    await deleteDeviceDict(props.resource, row.id)
    ui.toast('已删除', 'success')
    load()
  } catch (e) {
    ui.toast((e as Error).message, 'error')
  }
}

onMounted(() => {
  load()
  fetchEntityMeta('device_dictionary')
    .then((result) => { metadata.value = result })
    .catch(() => { /* 兼容滚动发布期间的旧后端 */ })
})
</script>

<style scoped>
.tab-toolbar {
  display: flex;
  justify-content: flex-end;
  margin-bottom: 10px;
}
</style>
