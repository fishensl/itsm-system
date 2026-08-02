import { createRouter, createWebHistory, type RouteRecordRaw } from 'vue-router'
import { useUserStore } from '@/stores/user'

const routes: RouteRecordRaw[] = [
  {
    path: '/login',
    name: 'login',
    component: () => import('@/views/login/index.vue'),
    meta: { public: true, title: '登录' },
  },
  {
    path: '/',
    component: () => import('@/layouts/MainLayout.vue'),
    children: [
      {
        path: '',
        name: 'dashboard',
        component: () => import('@/views/dashboard/index.vue'),
        meta: { title: '工作台' },
      },
    ],
  },
  // 未匹配 → 工作台（SPA 内无 404 页面时兜底）
  { path: '/:pathMatch(.*)*', redirect: '/' },
]

const router = createRouter({
  history: createWebHistory('/app/'),
  routes,
})

// 路由守卫：未登录跳登录页（public 路由除外）
router.beforeEach(async (to) => {
  const userStore = useUserStore()
  if (to.meta.public) {
    if (userStore.isAuthenticated && to.name === 'login') return { path: '/' }
    return true
  }
  if (!userStore.loaded) {
    await userStore.init()
  }
  if (!userStore.isAuthenticated) {
    return { path: '/login', query: { redirect: to.fullPath } }
  }
  return true
})

router.afterEach((to) => {
  document.title = `${String(to.meta.title || '')} - IT运维综合管理系统`
})

export default router
