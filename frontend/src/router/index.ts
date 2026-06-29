import { createRouter, createWebHashHistory } from 'vue-router'
import { usePreFlightStore } from '@/stores/preflight'
import DashboardView from '@/views/DashboardView.vue'

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
    {
      path: '/dashboard',
      name: 'dashboard',
      component: DashboardView,
      meta: { requiresProbe: true },
    },
  ],
})

router.beforeEach((to, _from, next) => {
  const preflight = usePreFlightStore()

  // /boot 始终允许
  if (to.name === 'boot') {
    if (preflight.status === 'passed') {
      return next({ name: 'dashboard' })
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
