<template>
  <div class="layout">
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
                  <template
                    v-for="c in childrenFor(grp)"
                    :key="c.url"
                  >
                    <router-link
                      :to="c.target.path + c.target.query"
                      class="sidebar-link"
                      :class="{ active: isActive(c.url) }"
                    >
                      <el-icon><component :is="c.icon" /></el-icon>
                      <span v-show="!ui.sidebarCollapsed">{{ c.name }}</span>
                    </router-link>
                  </template>
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
          <!-- 全局搜索 -->
          <GlobalSearch class="global-search" />
          <!-- 通知铃铛 -->
          <NotificationBell class="notif-bell" />
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
        @click="mobileNotif = true"
      >
        <el-icon><Bell /></el-icon><span>消息</span>
      </div>
      <div
        class="bottom-nav-item"
        @click="mobileSearch = true"
      >
        <el-icon><Search /></el-icon><span>搜索</span>
      </div>
      <div
        class="bottom-nav-item"
        @click="ui.mobileSidebarOpen = true"
      >
        <el-icon><Menu /></el-icon><span>菜单</span>
      </div>
    </nav>

    <!-- 移动端全屏搜索层 -->
    <div v-if="mobileSearch" class="mobile-search-layer" @click.self="mobileSearch = false">
      <GlobalSearch />
    </div>

    <!-- 移动端通知抽屉 -->
    <el-drawer v-model="mobileNotif" title="通知" size="85%">
      <NotificationBell :inline="true" />
    </el-drawer>

    <!-- 修改密码弹窗 -->
    <el-dialog v-model="pwdVisible" title="修改密码" width="420px" destroy-on-close>
      <el-form ref="pwdFormRef" :model="pwdForm" label-width="90px">
        <el-form-item label="原密码" prop="old_password"
          :rules="[{ required: true, message: '请输入原密码', trigger: 'blur' }]">
          <el-input v-model="pwdForm.old_password" type="password" show-password autocomplete="current-password" />
        </el-form-item>
        <el-form-item label="新密码" prop="new_password"
          :rules="[{ required: true, message: '请输入新密码', trigger: 'blur' },
                   { min: 6, message: '至少 6 位', trigger: 'blur' }]">
          <el-input v-model="pwdForm.new_password" type="password" show-password autocomplete="new-password" />
        </el-form-item>
        <el-form-item label="确认密码" prop="confirm"
          :rules="[{ required: true, message: '请再次输入新密码', trigger: 'blur' },
                   { validator: confirmValidator, trigger: 'blur' }]">
          <el-input v-model="pwdForm.confirm" type="password" show-password autocomplete="new-password" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="pwdVisible = false">取消</el-button>
        <el-button type="primary" :loading="pwdSaving" @click="savePassword">确认修改</el-button>
      </template>
    </el-dialog>

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
    <OpVerifyDialog />
  </div>
</template>

<script setup lang="ts">
import { ElMessageBox } from 'element-plus/es/components/message-box/index'
import { ref, computed, reactive, onMounted, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import {
  Monitor, Expand, Fold, Menu, ArrowDown, MoonNight, Sunny,
  SwitchButton, HomeFilled, Bell, Search,
} from '@element-plus/icons-vue'
import GlobalSearch from '@/components/GlobalSearch.vue'
import NotificationBell from '@/components/NotificationBell.vue'
import OpVerifyDialog from '@/components/OpVerifyDialog.vue'
import { sidebarTarget, isRouteActive } from '@/utils/sidebarNav'
import { loadOpenGroups, saveOpenGroups, clearOpenGroups } from '@/utils/sidebarState'
import { changePassword } from '@/api/auth'
import type { SidebarGroup } from '@/types'
import { useUserStore } from '@/stores/user'
import { useUiStore } from '@/stores/ui'

const route = useRoute()
const router = useRouter()
const user = useUserStore()
const ui = useUiStore()

const mobileNotif = ref(false)
const mobileSearch = ref(false)
// 路由跳转后自动关闭移动端搜索层（GlobalSearch 内部 go 跳转）
watch(() => route.fullPath, () => {
  mobileSearch.value = false
})
// 展开分组：从 sessionStorage 恢复，刷新后保持用户操作状态
const openGroups = ref<Set<string>>(new Set(loadOpenGroups()))
const theme = ref<'light' | 'dark'>(localStorage.getItem('appTheme') === 'dark' ? 'dark' : 'light')

const avatarText = computed(() => {
  const name = user.user?.realname || user.user?.username || 'U'
  return name.slice(0, 1).toUpperCase()
})

const isActive = (url: string) => isRouteActive(route.path, route.query, url)

/** 侧栏链接目标：统一规范为 SPA 内部路由 */
const childrenFor = (grp: SidebarGroup) =>
  grp.children
    .filter((x) => user.hasPerm(x.perm))
    .map((c) => ({ ...c, target: sidebarTarget(c.url) }))

const toggleGroup = (key: string) => {
  const next = new Set(openGroups.value)
  if (next.has(key)) next.delete(key)
  else next.add(key)
  openGroups.value = next
  saveOpenGroups([...next])
}

const applyTheme = (t: 'light' | 'dark') => {
  document.documentElement.classList.toggle('dark', t === 'dark')
}

const toggleTheme = () => {
  theme.value = theme.value === 'light' ? 'dark' : 'light'
  localStorage.setItem('appTheme', theme.value)
  applyTheme(theme.value)
}

const handleLogout = async () => {
  try {
    await ElMessageBox.confirm('确定要退出登录吗？', '提示', { type: 'warning' })
  } catch {
    return
  }
  clearOpenGroups()
  await user.logout()
  router.push('/login')
}

const onUserCommand = (cmd: string) => {
  if (cmd === 'logout') handleLogout()
  else if (cmd === 'password') openPwdDialog()
}

// 修改密码（SPA 弹窗，替代 /me/change_password 整页跳转）
const pwdVisible = ref(false)
const pwdSaving = ref(false)
const pwdFormRef = ref()
const pwdForm = reactive({ old_password: '', new_password: '', confirm: '' })

const confirmValidator = (_r: unknown, v: string, cb: (e?: Error) => void) => {
  if (v === pwdForm.new_password) cb()
  else cb(new Error('两次输入不一致'))
}

function openPwdDialog() {
  pwdForm.old_password = ''
  pwdForm.new_password = ''
  pwdForm.confirm = ''
  pwdVisible.value = true
}

async function savePassword() {
  try { await pwdFormRef.value?.validate() } catch { return }
  pwdSaving.value = true
  try {
    await changePassword(pwdForm.old_password, pwdForm.new_password)
    ui.toast('密码已修改，请重新登录', 'success')
    pwdVisible.value = false
    await user.logout()
    router.push('/login')
  } catch (e) {
    ui.toast((e as Error).message, 'error')
  } finally {
    pwdSaving.value = false
  }
}

/** 当前路由所在分组（用于首次进入自动展开） */
const activeGroupKey = computed(() => {
  for (const grp of user.sidebarGroups) {
    const urls = grp.single_link ? [grp.single_link.url] : grp.children.map((c) => c.url)
    const hit = urls.some((u) => {
      const p = (u.split('?')[0].replace(/^\/app/, '').replace(/\/+$/, '')) || '/'
      return p === route.path
    })
    if (hit) return grp.key
  }
  return null
})

onMounted(() => {
  applyTheme(theme.value)
  // 首次进入：自动展开当前路由所在分组（防直接访问子页面时全折叠）
  const key = activeGroupKey.value
  if (key && !openGroups.value.has(key)) {
    const next = new Set(openGroups.value)
    next.add(key)
    openGroups.value = next
    saveOpenGroups([...next])
  }
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
    display: none; /* 移动端用全屏搜索层（mobile-search-layer）替代 */
  }
  /* S7-4 移动端全屏搜索层 */
  .mobile-search-layer {
    position: fixed;
    inset: 0;
    z-index: 1200;
    background: var(--itsm-bg);
    padding: 12px;
    padding-top: max(16px, env(safe-area-inset-top));
    overflow-y: auto;
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
