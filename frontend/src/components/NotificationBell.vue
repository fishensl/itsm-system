<template>
  <!-- inline 模式：直接渲染完整列表（移动端抽屉用），否则为铃铛 popover -->
  <div v-if="inline" class="notif-inline">
    <div class="notif-header">
      <span class="notif-title">通知</span>
      <el-button v-if="unread > 0" link type="primary" size="small" @click="readAll">
        全部已读
      </el-button>
    </div>
    <div v-if="items.length" class="notif-list">
      <div
        v-for="n in items"
        :key="n.id"
        class="notif-item"
        :class="{ unread: !n.is_read }"
        @click="open(n)"
      >
        <div class="notif-item-title">
          <span class="notif-dot" v-if="!n.is_read"></span>
          <b>{{ n.title }}</b>
          <span class="notif-time">{{ n.created_at }}</span>
        </div>
        <div v-if="n.content" class="notif-item-content">{{ n.content }}</div>
      </div>
    </div>
    <el-empty v-else description="暂无通知" :image-size="50" />
  </div>

  <el-popover v-else v-model:visible="visible" placement="bottom-end" :width="360" trigger="click" popper-class="notif-popover">
    <template #reference>
      <el-badge :value="unread" :hidden="unread === 0" :max="99" class="notif-badge">
        <el-button text :icon="Bell" @click="load" />
      </el-badge>
    </template>
    <div class="notif-panel">
      <div class="notif-header">
        <span class="notif-title">通知</span>
        <el-button v-if="unread > 0" link type="primary" size="small" @click="readAll">
          全部已读
        </el-button>
      </div>
      <div v-if="items.length" class="notif-list">
        <div
          v-for="n in items"
          :key="n.id"
          class="notif-item"
          :class="{ unread: !n.is_read }"
          @click="open(n)"
        >
          <div class="notif-item-title">
            <span class="notif-dot" v-if="!n.is_read"></span>
            <b>{{ n.title }}</b>
            <span class="notif-time">{{ n.created_at }}</span>
          </div>
          <div v-if="n.content" class="notif-item-content">{{ n.content }}</div>
        </div>
      </div>
      <el-empty v-else description="暂无通知" :image-size="50" />
    </div>
  </el-popover>
</template>

<script setup lang="ts">
import { ref, onMounted, onBeforeUnmount, watch } from 'vue'
import { useRouter } from 'vue-router'
import { Bell } from '@element-plus/icons-vue'
import {
  fetchNotifications, fetchUnreadCount, markRead, type NotificationItem,
} from '@/api/notifications'

const props = withDefaults(defineProps<{ inline?: boolean }>(), { inline: false })
const router = useRouter()
const visible = ref(false)
const items = ref<NotificationItem[]>([])
const unread = ref(0)

async function load() {
  try {
    const [list, cnt] = await Promise.all([fetchNotifications(), fetchUnreadCount()])
    items.value = list.items
    unread.value = cnt.unread
  } catch { /* toast */ }
}

async function open(n: NotificationItem) {
  if (!n.is_read) {
    await markRead([n.id])
    n.is_read = true
    unread.value = Math.max(0, unread.value - 1)
  }
  visible.value = false
  if (n.link) {
    if (n.link.startsWith('/app')) router.push(n.link.replace('/app', ''))
    else window.location.href = n.link
  }
}

async function readAll() {
  await markRead()
  items.value.forEach((n) => (n.is_read = true))
  unread.value = 0
}

let timer: ReturnType<typeof setInterval> | undefined
onMounted(() => {
  load()
  // inline 模式（移动端抽屉内的第二实例）不重复轮询，仅顶栏铃铛实例轮询
  if (!props.inline) timer = setInterval(load, 60000) // 每分钟轮询未读数
})
onBeforeUnmount(() => clearInterval(timer))

// inline 模式：抽屉打开时加载
watch(
  () => props.inline,
  (v) => {
    if (v) load()
  },
  { immediate: true },
)
</script>

<style scoped>
.notif-badge {
  display: inline-flex;
}
.notif-panel {
  max-height: 420px;
  display: flex;
  flex-direction: column;
}
.notif-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 4px 8px 8px;
  border-bottom: 1px solid var(--itsm-border);
}
.notif-title {
  font-weight: 600;
  font-size: 14px;
}
.notif-list {
  overflow-y: auto;
  max-height: 360px;
}
.notif-item {
  padding: 8px;
  border-bottom: 1px dashed var(--itsm-border);
  cursor: pointer;
}
.notif-item:hover {
  background: var(--el-fill-color-light);
}
.notif-item.unread {
  background: var(--el-color-primary-light-9);
}
.notif-item-title {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
}
.notif-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--el-color-danger);
  flex-shrink: 0;
}
.notif-time {
  margin-left: auto;
  color: var(--itsm-text-muted);
  font-size: 11px;
  flex-shrink: 0;
}
.notif-item-content {
  font-size: 12px;
  color: var(--itsm-text-muted);
  margin-top: 2px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
</style>
