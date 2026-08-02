<template>
  <div
    class="layout"
    :data-theme="theme"
  >
    <!-- 移动端抽屉遮罩 -->
    <div
      v-if="ui.mobileSidebarOpen"
      class="sidebar-overlay"
      @click="ui.mobileSidebarOpen = false"
    />

    <!-- 侧栏 -->
    <aside
      class="sidebar"
      :class="{ collapsed: ui.sidebarCollapsed, 'mobile-open': ui.mobileSidebarOpen }"
    >
      <div class="sidebar-header">
        <el-icon
          :size="22"
          color="#2563eb"
        >
          <Monitor />
        </el-icon>
        <span
          v-show="!ui.sidebarCollapsed"
          class="sidebar-title"
        >IT运维综合管理系统</span>
        <el-button
          class="sidebar-toggle"
          text
          :icon="ui.sidebarCollapsed ? Expand : Fold"
          @click="ui.toggleSidebar()"
        />
      </div>

      <el-scrollbar class="sidebar-scroll">
        <nav class="sidebar-nav">
          <template
            v-for="grp in user.sidebarGroups"
            :key="grp.key"
          >
            <!-- 单链接组（工作台） -->
            <router-link
              v-if="grp.single_link"
              :to="grp.single_link.url.replace('/app', '') || '/'"
              class="sidebar-link"
              :class="{ active: isActive(grp.single_link.url) }"
            >
              <el-icon><component :is="grp.single_link.icon || grp.icon" /></el-icon>
              <span v-show="!ui.sidebarCollapsed">{{ grp.single_link.name }}</span>
            </router-link>

            <!-- 多子项组 -->
            <template v-else>
              <div
                class="sidebar-group"
                :class="{ open: openGroups.has(grp.key) }"
              >
                <div
                  class="sidebar-group-title"
                  @click="toggleGroup(grp.key)"
                >
                  <el-icon><component :is="grp.icon" /></el-icon>
                  <span v-show="!ui.sidebarCollapsed">{{ grp.title }}</span>
                  <el-icon
                    v-show="!ui.sidebarCollapsed"
                    class="group-arrow"
                  >
                    <ArrowDown />
                  </el-icon>
                </div>
                <div
                  v-show="openGroups.has(grp.key)"
                  class="sidebar-children"
                >
                  <router-link
                    v-for="c in grp.children.filter((x) => user.hasPerm(x.perm))"
                    :key="c.url"
                    :to="toAppPath(c.url)"
                    class="sidebar-link"
                    :class="{ active: isActive(c.url) }"
                  >
                    <el-icon><component :is="c.icon" /></el-icon>
                    <span v-show="!ui.sidebarCollapsed">{{ c.name }}</span>
                  </router-link>
                </div>
              </div>
            </template>
          </template>
        </nav>
      </el-scrollbar>

      <div class="sidebar-footer">
        <div
          class="sidebar-link"
          @click="toggleTheme"
        >
          <el-icon><MoonNight v-if="theme === 'light'" /><Sunny v-else /></el-icon>
          <span v-show="!ui.sidebarCollapsed">{{ theme === 'light' ? '深色模式' : '浅色模式' }}</span>
        </div>
        <div
          class="sidebar-link"
          @click="handleLogout"
        >
          <el-icon><SwitchButton /></el-icon>
          <span v-show="!ui.sidebarCollapsed">退出登录</span>
        </div>
      </div>
    </aside>

    <!-- 主区 -->
    <div class="main">
      <!-- 顶栏 -->
      <header class="topbar">
        <el-button
          class="mobile-menu-btn"
          text
          :icon="Menu"
          @click="ui.mobileSidebarOpen = true"
        />
        <div class="topbar-title">
          {{ route.meta.title }}
        </div>
        <div class="topbar-right">
          <!-- 全局搜索（P3 实现） -->
          <el-input
            v-model="searchText"
            class="global-search"
            placeholder="搜索设备/客户/工单/知识库..."
            :prefix-icon="Search"
            clearable
          />
          <!-- 通知铃铛（P3 实现） -->
          <el-badge
            :value="0"
            :hidden="true"
            class="notif-badge"
          >
            <el-button
              text
              :icon="Bell"
              @click="notifOpen = true"
            />
          </el-badge>
          <!-- 用户菜单 -->
          <el-dropdown @command="onUserCommand">
            <span class="user-chip">
              <el-avatar
                :size="28"
                class="user-avatar"
              >{{ avatarText }}</el-avatar>
              <span class="user-name">{{ user.user?.realname || user.user?.username }}</span>
              <el-icon><ArrowDown /></el-icon>
            </span>
            <template #dropdown>
              <el-dropdown-menu>
                <el-dropdown-item command="password">
                  修改密码
                </el-dropdown-item>
                <el-dropdown-item
                  command="logout"
                  divided
                >
                  退出登录
                </el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>
        </div>
      </header>

      <!-- 内容 -->
      <main class="content">
        <router-view />
      </main>
    </div>

    <!-- 移动端底部导航 -->
    <nav class="bottom-nav">
      <router-link
        to="/"
        class="bottom-nav-item"
        :class="{ active: route.path === '/' }"
      >
        <el-icon><HomeFilled /></el-icon><span>工作台</span>
      </router-link>
      <div
        class="bottom-nav-item"
        @click="notifOpen = true"
      >
        <el-icon><Bell /></el-icon><span>消息</span>
      </div>
      <div
        class="bottom-nav-item"
        @click="ui.mobileSidebarOpen = true"
      >
        <el-icon><Menu /></el-icon><span>菜单</span>
      </div>
    </nav>

    <!-- Toast 容器 -->
    <div class="toast-wrap">
      <el-alert
        v-for="t in ui.toasts"
        :key="t.id"
        :title="t.message"
        :type="t.type"
        :closable="false"
        class="toast-item"
      />
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessageBox } from 'element-plus'
import {
  Monitor, Expand, Fold, Menu, Search, Bell, ArrowDown, MoonNight, Sunny,
  SwitchButton, HomeFilled,
} from '@element-plus/icons-vue'
import { useUserStore } from '@/stores/user'
import { useUiStore } from '@/stores/ui'

const route = useRoute()
const router = useRouter()
const user = useUserStore()
const ui = useUiStore()

const searchText = ref('')
const notifOpen = ref(false)
const openGroups = ref(new Set<string>())
const theme = ref<'light' | 'dark'>(localStorage.getItem('appTheme') === 'dark' ? 'dark' : 'light')

const avatarText = computed(() => {
  const name = user.user?.realname || user.user?.username || 'U'
  return name.slice(0, 1).toUpperCase()
})

const isActive = (url: string) => {
  const path = url.split('?')[0].replace('/app', '')
  return route.path === path
}

const toAppPath = (url: string) => {
  // 已迁移到 /app 的页面直接跳 /app；未迁移的（P1 阶段仅工作台）跳 SSR 原路径
  const migrated = ['/'].includes(url)
  return migrated ? url.replace('/app', '') : url
}

const toggleGroup = (key: string) => {
  const next = new Set(openGroups.value)
  if (next.has(key)) next.delete(key)
  else next.add(key)
  openGroups.value = next
}

const toggleTheme = () => {
  theme.value = theme.value === 'light' ? 'dark' : 'light'
  localStorage.setItem('appTheme', theme.value)
  document.documentElement.setAttribute('data-theme', theme.value)
}

const handleLogout = async () => {
  try {
    await ElMessageBox.confirm('确定要退出登录吗？', '提示', { type: 'warning' })
  } catch {
    return
  }
  await user.logout()
  router.push('/login')
}

const onUserCommand = (cmd: string) => {
  if (cmd === 'logout') handleLogout()
  else if (cmd === 'password') window.location.href = '/me/change_password'
}

onMounted(() => {
  document.documentElement.setAttribute('data-theme', theme.value)
})
</script>

<style scoped>
.layout {
  display: flex;
  height: 100vh;
  overflow: hidden;
}

/* 侧栏 */
.sidebar {
  width: var(--itsm-sidebar-width);
  background: var(--itsm-card-bg);
  border-right: 1px solid var(--itsm-border);
  display: flex;
  flex-direction: column;
  transition: width 0.2s;
  flex-shrink: 0;
}
.sidebar.collapsed {
  width: var(--itsm-sidebar-collapsed);
}
.sidebar-header {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 14px 12px;
  border-bottom: 1px solid var(--itsm-border);
}
.sidebar-title {
  font-weight: 600;
  font-size: 14px;
  white-space: nowrap;
  overflow: hidden;
}
.sidebar-toggle {
  margin-left: auto;
}
.sidebar-scroll {
  flex: 1;
}
.sidebar-nav {
  padding: 8px;
}
.sidebar-group-title,
.sidebar-link {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 9px 12px;
  border-radius: 6px;
  cursor: pointer;
  color: var(--itsm-text);
  text-decoration: none;
  font-size: 13px;
  white-space: nowrap;
}
.sidebar-link:hover,
.sidebar-group-title:hover {
  background: var(--el-fill-color-light);
}
.sidebar-link.active {
  background: var(--el-color-primary-light-9);
  color: var(--itsm-primary);
}
.group-arrow {
  margin-left: auto;
  transition: transform 0.2s;
  font-size: 12px;
}
.sidebar-group.open .group-arrow {
  transform: rotate(180deg);
}
.sidebar-children .sidebar-link {
  padding-left: 34px;
}
.sidebar-footer {
  border-top: 1px solid var(--itsm-border);
  padding: 8px;
}

/* 主区 */
.main {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-width: 0;
}
.topbar {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 0 16px;
  height: 52px;
  background: var(--itsm-card-bg);
  border-bottom: 1px solid var(--itsm-border);
}
.mobile-menu-btn {
  display: none;
}
.topbar-title {
  font-weight: 600;
  font-size: 15px;
}
.topbar-right {
  margin-left: auto;
  display: flex;
  align-items: center;
  gap: 8px;
}
.global-search {
  width: 260px;
}
.user-chip {
  display: flex;
  align-items: center;
  gap: 6px;
  cursor: pointer;
  outline: none;
}
.user-avatar {
  background: var(--itsm-primary);
  color: #fff;
  font-size: 13px;
}
.content {
  flex: 1;
  overflow-y: auto;
}

/* 移动端遮罩 */
.sidebar-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.45);
  z-index: 900;
}

/* 移动端底部导航 */
.bottom-nav {
  display: none;
}

/* Toast */
.toast-wrap {
  position: fixed;
  top: 60px;
  right: 16px;
  z-index: 3000;
  display: flex;
  flex-direction: column;
  gap: 8px;
  max-width: min(360px, calc(100vw - 32px));
}
.toast-item {
  animation: toast-in 0.2s;
}
@keyframes toast-in {
  from { opacity: 0; transform: translateX(20px); }
  to { opacity: 1; transform: translateX(0); }
}

/* ============ 移动端（<768px） ============ */
@media (max-width: 767px) {
  .sidebar {
    position: fixed;
    left: 0;
    top: 0;
    bottom: 0;
    z-index: 1000;
    width: 260px !important;
    transform: translateX(-100%);
    transition: transform 0.25s;
  }
  .sidebar.mobile-open {
    transform: translateX(0);
  }
  .mobile-menu-btn {
    display: inline-flex;
  }
  .global-search {
    display: none; /* P3 移动端做全屏搜索层 */
  }
  .user-name {
    display: none;
  }
  .bottom-nav {
    position: fixed;
    left: 0;
    right: 0;
    bottom: 0;
    z-index: 950;
    display: flex;
    background: var(--itsm-card-bg);
    border-top: 1px solid var(--itsm-border);
    padding-bottom: env(safe-area-inset-bottom);
  }
  .bottom-nav-item {
    flex: 1;
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 2px;
    padding: 8px 0;
    font-size: 11px;
    color: var(--itsm-text-muted);
    cursor: pointer;
    text-decoration: none;
  }
  .bottom-nav-item.active {
    color: var(--itsm-primary);
  }
  .notif-badge {
    display: none;
  }
}
</style>
