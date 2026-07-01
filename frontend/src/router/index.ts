import { createRouter, createWebHashHistory } from 'vue-router'
import { usePreFlightStore } from '@/stores/preflight'

const router = createRouter({
  // WHY hash history：生产部署时 FastAPI 托管静态文件，
  // hash 模式无需后端配置 SPA fallback。
  history: createWebHashHistory(),
  routes: [
    {
      path: '/',
      redirect: '/boot',
    },
    {
      path: '/boot',
      name: 'boot',
      component: () => import('@/views/BootView.vue'),
    },
    // Step 10 新路由——单页面板 TerminalShell
    {
      path: '/app',
      name: 'app',
      component: () => import('@/views/TerminalShell.vue'),
      meta: { requiresProbe: true },
    },
    // WHY 旧路由保留至 Phase G：开发期间可回退验证
    {
      path: '/dashboard',
      name: 'dashboard',
      component: () => import('@/views/DashboardView.vue'),
      meta: { requiresProbe: true },
    },
    {
      path: '/review/:taskId',
      name: 'review',
      component: () => import('@/views/ReviewView.vue'),
      meta: { requiresProbe: true },
    },
    {
      path: '/review/:taskId/:file',
      name: 'review-file',
      component: () => import('@/views/ReviewView.vue'),
      meta: { requiresProbe: true },
    },
  ],
})

router.beforeEach((to, _from, next) => {
  const preflight = usePreFlightStore()

  // /boot 始终允许
  if (to.name === 'boot') {
    if (preflight.status === 'passed') {
      return next({ name: 'app' })  // Step 10: 预检通过 → /app
    }
    return next()
  }

  // 需要预检通过的路由
  if (to.meta?.requiresProbe && preflight.status !== 'passed') {
    return next({ name: 'boot' })
  }

  next()
})

export default router
