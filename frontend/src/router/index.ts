import { createRouter, createWebHistory, type RouteRecordRaw } from 'vue-router'
import { useUserStore } from '@/stores/user'

// 扩展路由 meta 类型
declare module 'vue-router' {
  interface RouteMeta {
    title?: string
    perm?: string
    public?: boolean
  }
}

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
      {
        path: 'customers',
        name: 'customers',
        component: () => import('@/views/customers/index.vue'),
        meta: { title: '客户管理', perm: 'customer:view' },
      },
      {
        path: 'devices',
        name: 'devices',
        component: () => import('@/views/devices/index.vue'),
        meta: { title: '设备管理', perm: 'device:view' },
      },
      {
        path: 'devices/:id(\\d+)',
        name: 'device-detail',
        component: () => import('@/views/devices/index.vue'),
        meta: { title: '设备详情', perm: 'device:view' },
      },
      {
        path: 'tickets',
        name: 'tickets',
        component: () => import('@/views/tickets/index.vue'),
        meta: { title: '工单管理', perm: 'ticket:view' },
      },
      {
        path: 'tickets/:id(\\d+)',
        name: 'ticket-detail',
        component: () => import('@/views/tickets/index.vue'),
        meta: { title: '工单详情', perm: 'ticket:view' },
      },
      {
        path: 'task-board',
        name: 'task-board',
        component: () => import('@/views/taskBoard/index.vue'),
        meta: { title: '任务看板', perm: 'task:schedule' },
      },
      {
        path: 'inspections',
        name: 'inspections',
        component: () => import('@/views/inspections/index.vue'),
        meta: { title: '巡检记录', perm: 'inspection:view' },
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
  // 页面级权限校验
  const perm = to.meta.perm as string | undefined
  if (perm && !userStore.hasPerm(perm)) {
    return { path: '/' }
  }
  return true
})

router.afterEach((to) => {
  document.title = `${String(to.meta.title || '')} - IT运维综合管理系统`
})

export default router
