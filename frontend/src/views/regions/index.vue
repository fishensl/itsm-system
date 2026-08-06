<template>
  <div class="page-container">
    <div class="page-header">
      <h2 class="page-title">地区管理</h2>
      <div class="header-actions">
        <el-button v-if="user.hasPerm('region:add')" type="primary" :icon="Plus" @click="openCreate(null)">
          新增地市
        </el-button>
      </div>
    </div>

    <el-card shadow="never">
      <div v-loading="loading" class="region-tree">
        <div v-for="city in cities" :key="city.id" class="city-block">
          <div class="city-row" @click="toggleCity(city.id)">
            <el-icon class="collapse-arrow" :class="{ expanded: isCityExpanded(city.id) }">
              <ArrowRight />
            </el-icon>
            <el-icon color="#2563eb"><OfficeBuilding /></el-icon>
            <span class="city-name">{{ city.name }}</span>
            <el-tag v-if="city.children?.length" size="small" type="info">{{ city.children.length }} 区县</el-tag>
            <span class="row-actions" @click.stop>
              <el-button v-if="user.hasPerm('region:add')" size="small" link type="primary"
                @click="openCreate(city)">+ 区县</el-button>
              <el-button v-if="user.hasPerm('region:edit')" size="small" link type="primary"
                @click="openEdit(city)">编辑</el-button>
              <el-button v-if="user.hasPerm('region:delete')" size="small" link type="danger"
                @click="onDelete(city)">删除</el-button>
            </span>
          </div>
          <div v-if="city.children?.length" v-show="isCityExpanded(city.id)" class="district-list">
            <div v-for="d in city.children" :key="d.id" class="district-row">
              <el-icon><Location /></el-icon>
              <span class="district-name">{{ d.name }}</span>
              <span class="row-actions">
                <el-button v-if="user.hasPerm('region:edit')" size="small" link type="primary"
                  @click="openEdit(d)">编辑</el-button>
                <el-button v-if="user.hasPerm('region:delete')" size="small" link type="danger"
                  @click="onDelete(d)">删除</el-button>
              </span>
            </div>
          </div>
        </div>
      </div>
      <el-empty v-if="!loading && !cities.length" description="暂无地区，请先新增地市" :image-size="60" />
    </el-card>

    <el-dialog v-model="formVisible" :title="form.id ? '编辑地区' : (form.parent_id ? '新增区县' : '新增地市')"
      width="420px" destroy-on-close>
      <el-form ref="formRef" :model="form" label-width="90px">
        <el-form-item label="地区名称" prop="name" :rules="[{ required: true, message: '请输入名称', trigger: 'blur' }]">
          <el-input v-model="form.name" placeholder="名称" />
        </el-form-item>
        <el-form-item v-if="form.id" label="所属地市">
          <el-select v-model="form.parent_id" clearable placeholder="无（作为地市）" style="width: 100%">
            <el-option v-for="c in cities.filter((x) => x.id !== form.id)" :key="c.id" :label="c.name" :value="c.id" />
          </el-select>
        </el-form-item>
        <el-form-item v-if="form.id" label="排序">
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
import { Plus, OfficeBuilding, Location, ArrowRight } from '@element-plus/icons-vue'
import { fetchRegions, createRegion, updateRegion, deleteRegion, type RegionItem } from '@/api/regions'
import { useUserStore } from '@/stores/user'
import { useUiStore } from '@/stores/ui'

const user = useUserStore()
const ui = useUiStore()
const cities = ref<RegionItem[]>([])
const loading = ref(false)
const formVisible = ref(false)
const saving = ref(false)
const formRef = ref()
const form = reactive<Record<string, unknown>>({ id: null, name: '', parent_id: null, sort_order: 0 })

// 市级默认折叠，点击城市行展开/收起区县
const expandedCityIds = ref<Set<number>>(new Set())

function isCityExpanded(id: number) {
  return expandedCityIds.value.has(id)
}

function toggleCity(id: number) {
  const next = new Set(expandedCityIds.value)
  if (next.has(id)) next.delete(id)
  else next.add(id)
  expandedCityIds.value = next
}

function load() {
  loading.value = true
  fetchRegions()
    .then((d) => { cities.value = d })
    .catch(() => { /* toast */ })
    .finally(() => { loading.value = false })
}

function openCreate(parent: RegionItem | null) {
  Object.assign(form, { id: null, name: '', parent_id: parent?.id ?? null, sort_order: 0 })
  formVisible.value = true
}

function openEdit(row: RegionItem) {
  Object.assign(form, { id: row.id, name: row.name, parent_id: row.parent_id, sort_order: row.sort_order })
  formVisible.value = true
}

async function save() {
  try { await formRef.value?.validate() } catch { return }
  saving.value = true
  try {
    if (form.id) {
      await updateRegion(form.id as number, {
        name: String(form.name), parent_id: (form.parent_id as number | null) ?? null, sort_order: Number(form.sort_order || 0),
      })
      ui.toast('已保存', 'success')
    } else {
      await createRegion({ name: String(form.name), parent_id: (form.parent_id as number | null) ?? null })
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

async function onDelete(row: RegionItem) {
  try {
    await ElMessageBox.confirm(`确定删除地区「${row.name}」吗？`, '删除确认', { type: 'warning' })
  } catch { return }
  try {
    await deleteRegion(row.id)
    ui.toast('已删除', 'success')
    load()
  } catch (e) {
    ui.toast((e as Error).message, 'error')
  }
}

onMounted(load)
</script>

<style scoped>
.region-tree { min-height: 80px; }
.city-block { border: 1px solid var(--itsm-border); border-radius: 8px; margin-bottom: 10px; overflow: hidden; }
.city-row {
  display: flex; align-items: center; gap: 8px; padding: 10px 12px;
  background: var(--el-fill-color-light); font-weight: 600;
  cursor: pointer;
}
.city-row:hover { background: var(--el-fill-color); }
.collapse-arrow { transition: transform 0.2s; font-size: 13px; color: var(--itsm-text-muted); }
.collapse-arrow.expanded { transform: rotate(90deg); }
.city-name { font-size: 14px; }
.row-actions { margin-left: auto; display: flex; gap: 4px; }
.district-list { padding: 4px 12px; }
.district-row { display: flex; align-items: center; gap: 8px; padding: 7px 4px; border-bottom: 1px dashed var(--itsm-border); font-size: 13px; }
.district-row:last-child { border-bottom: none; }
.district-name { color: var(--itsm-text); }
</style>
