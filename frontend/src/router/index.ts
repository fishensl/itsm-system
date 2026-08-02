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
      {
        path: 'knowledge-base',
        name: 'knowledge',
        component: () => import('@/views/knowledge/index.vue'),
        meta: { title: '知识库', perm: 'kb:view' },
      },
      {
        path: 'faults',
        name: 'faults',
        component: () => import('@/views/faults/index.vue'),
        meta: { title: '故障记录', perm: 'fault:view' },
      },
      {
        path: 'reports',
        name: 'reports',
        component: () => import('@/views/reports/index.vue'),
        meta: { title: '报告管理', perm: 'report:view' },
      },
      {
        path: 'spare-parts',
        name: 'spare',
        component: () => import('@/views/spare/index.vue'),
        meta: { title: '备件管理', perm: 'spare:view' },
      },
      {
        path: 'sales',
        name: 'sales',
        component: () => import('@/views/sales/index.vue'),
        meta: { title: '销售管理', perm: 'sales:view' },
      },
      {
        path: 'rack',
        name: 'rack',
        component: () => import('@/views/rack/index.vue'),
        meta: { title: '机柜管理', perm: 'device:view' },
      },
      {
        path: 'topologies',
        name: 'topologies',
        component: () => import('@/views/topology/index.vue'),
        meta: { title: '拓扑图', perm: 'topology:view' },
      },
      {
        path: 'tools',
        name: 'tools',
        component: () => import('@/views/tools/index.vue'),
        meta: { title: '网络工具' },
      },
      {
        path: 'system/users',
        name: 'sys-users',
        component: () => import('@/views/system/users.vue'),
        meta: { title: '用户与部门', perm: 'user:view' },
      },
      {
        path: 'system/audit',
        name: 'sys-audit',
        component: () => import('@/views/system/audit.vue'),
        meta: { title: '审计日志', perm: 'user:view' },
      },
      {
        path: 'system/overview',
        name: 'sys-overview',
        component: () => import('@/views/system/overview.vue'),
        meta: { title: '系统概览' },
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
