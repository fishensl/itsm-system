<template>
  <div class="page-container">
    <div class="page-header">
      <h2 class="page-title">侧栏自定义</h2>
      <div class="header-actions">
        <el-button plain @click="onReset">恢复默认</el-button>
        <el-button type="primary" :loading="saving" @click="save">保存</el-button>
      </div>
    </div>

    <el-card shadow="never">
      <div class="tip">调整分组顺序与启停，保存后侧栏即时生效（SSR 与 Vue 双端）。</div>
      <div v-loading="loading" class="group-list">
        <div v-for="(g, idx) in groups" :key="g.key" class="group-row">
          <span class="group-order">{{ idx + 1 }}</span>
          <span class="group-title">{{ g.title }}</span>
          <el-switch v-model="g.enabled" class="group-switch" />
          <el-button-group class="move-btns">
            <el-button size="small" :disabled="idx === 0" @click="move(idx, -1)">
              <el-icon><Top /></el-icon>
            </el-button>
            <el-button size="small" :disabled="idx === groups.length - 1" @click="move(idx, 1)">
              <el-icon><Bottom /></el-icon>
            </el-button>
          </el-button-group>
        </div>
      </div>
      <el-empty v-if="!loading && !groups.length" description="暂无分组" :image-size="60" />
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { ElMessageBox } from 'element-plus'
import { Top, Bottom } from '@element-plus/icons-vue'
import {
  fetchSidebarCustom, saveSidebarCustom, resetSidebarCustom, type SidebarCustomGroup,
} from '@/api/system'
import { useUiStore } from '@/stores/ui'

const ui = useUiStore()
const groups = ref<SidebarCustomGroup[]>([])
const loading = ref(false)
const saving = ref(false)

function load() {
  loading.value = true
  fetchSidebarCustom()
    .then((d) => { groups.value = d })
    .catch(() => { /* toast */ })
    .finally(() => { loading.value = false })
}

function move(idx: number, delta: number) {
  const target = idx + delta
  if (target < 0 || target >= groups.value.length) return
  const arr = groups.value
  ;[arr[idx], arr[target]] = [arr[target], arr[idx]]
  groups.value = [...arr]
}

async function save() {
  saving.value = true
  try {
    await saveSidebarCustom(groups.value)
    ui.toast('侧栏设置已保存', 'success')
  } catch (e) {
    ui.toast((e as Error).message, 'error')
  } finally {
    saving.value = false
  }
}

async function onReset() {
  try {
    await ElMessageBox.confirm('确定恢复为系统默认侧栏吗？', '恢复默认', { type: 'warning' })
  } catch { return }
  try {
    await resetSidebarCustom()
    ui.toast('已恢复默认', 'success')
    load()
  } catch (e) {
    ui.toast((e as Error).message, 'error')
  }
}

onMounted(load)
</script>

<style scoped>
.tip {
  font-size: 12px;
  color: var(--itsm-text-muted);
  margin-bottom: 12px;
}
.group-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.group-row {
  display: flex;
  align-items: center;
  gap: 12px;
  border: 1px solid var(--itsm-border);
  border-radius: 8px;
  padding: 10px 14px;
}
.group-title {
  font-size: 14px;
  font-weight: 500;
}
.group-order {
  font-size: 12px;
  color: var(--itsm-text-muted);
  min-width: 24px;
}
.group-switch {
  margin-left: auto;
}
</style>
