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
  // S7-8：403 无权限页（守卫跳转目标，替代静默踢回工作台）
  {
    path: '/403',
    name: 'forbidden',
    component: () => import('@/views/errors/Forbidden.vue'),
    meta: { title: '无权限' },
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
        path: 'customers/:id(\\d+)',
        name: 'customer-detail',
        component: () => import('@/views/customers/index.vue'),
        meta: { title: '客户详情', perm: 'customer:view' },
      },
      {
        path: 'regions',
        name: 'regions',
        component: () => import('@/views/regions/index.vue'),
        meta: { title: '地区管理', perm: 'region:view' },
      },
      {
        path: 'customer-categories',
        name: 'customer-categories',
        component: () => import('@/views/customerCategories/index.vue'),
        meta: { title: '单位类别', perm: 'category:view' },
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
        path: 'device-dicts',
        name: 'device-dicts',
        component: () => import('@/views/devices/dicts.vue'),
        meta: { title: '设备字典', perm: 'device:view' },
      },
      {
        path: 'device-firmwares',
        name: 'device-firmwares',
        component: () => import('@/views/firmwares/index.vue'),
        meta: { title: '固件版本库', perm: 'device:view' },
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
        path: 'task-schedule',
        name: 'task-schedule',
        component: () => import('@/views/taskSchedule/index.vue'),
        meta: { title: '任务安排', perm: 'task:schedule' },
      },
      {
        path: 'inspections',
        name: 'inspections',
        component: () => import('@/views/inspections/index.vue'),
        meta: { title: '巡检记录', perm: 'inspection:view' },
      },
      {
        path: 'inspections/:id(\\d+)',
        name: 'inspection-detail',
        component: () => import('@/views/inspections/index.vue'),
        meta: { title: '巡检详情', perm: 'inspection:view' },
      },
      {
        path: 'inspectors',
        name: 'inspectors',
        component: () => import('@/views/inspectors/index.vue'),
        meta: { title: '巡检人员', perm: 'inspection:view' },
      },
      {
        path: 'task-templates',
        name: 'task-templates',
        component: () => import('@/views/taskTemplates/index.vue'),
        meta: { title: '任务模板', perm: 'inspection:view' },
      },
      {
        path: 'device-check-templates',
        name: 'device-check-templates',
        component: () => import('@/views/deviceCheckTemplates/index.vue'),
        meta: { title: '设备模板', perm: 'inspection:view' },
      },
      {
        path: 'knowledge-base',
        name: 'knowledge',
        component: () => import('@/views/knowledge/index.vue'),
        meta: { title: '知识库', perm: 'kb:view' },
      },
      {
        path: 'knowledge-base/:id(\\d+)',
        name: 'knowledge-detail',
        component: () => import('@/views/knowledge/index.vue'),
        meta: { title: '知识详情', perm: 'kb:view' },
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
        path: 'contract-tasks',
        name: 'contract-tasks',
        component: () => import('@/views/contractTasks/index.vue'),
        meta: { title: '合同巡检配置', perm: 'contract_auto:manage' },
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
        path: 'system/export-reviews',
        name: 'sys-export-reviews',
        component: () => import('@/views/system/exportReviews.vue'),
        meta: { title: '导出审核', perm: 'user:view' },
      },
      {
        path: 'system/overview',
        name: 'sys-overview',
        component: () => import('@/views/system/overview.vue'),
        meta: { title: '系统概览' },
      },
      {
        path: 'system/sidebar',
        name: 'sys-sidebar',
        component: () => import('@/views/system/sidebar.vue'),
        meta: { title: '侧栏自定义' },
      },
      {
        path: 'ai-config',
        name: 'ai-config',
        component: () => import('@/views/system/aiConfig.vue'),
        meta: { title: 'AI 对接', perm: 'ai:view' },
      },
      {
        path: 'permissions',
        name: 'permissions',
        component: () => import('@/views/system/permissions.vue'),
        meta: { title: '权限管理', perm: 'permission:view' },
      },
      {
        path: 'system/backup',
        name: 'sys-backup',
        component: () => import('@/views/system/backup.vue'),
        meta: { title: '数据备份' },
      },
      {
        path: 'system/review-checklist',
        name: 'sys-review-checklist',
        component: () => import('@/views/system/ReviewChecklist.vue'),
        meta: { title: '巡检审核清单', perm: 'permission:edit' },
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
  // 页面级权限校验：无权限 → 403 提示（不再静默踢回工作台）
  const perm = to.meta.perm as string | undefined
  if (perm && !userStore.hasPerm(perm)) {
    import('element-plus').then(({ ElMessage }) => {
      ElMessage.warning('无访问权限')
    })
    return { path: '/403' }
  }
  return true
})

router.afterEach((to) => {
  document.title = `${String(to.meta.title || '')} - IT运维综合管理系统`
})

export default router
