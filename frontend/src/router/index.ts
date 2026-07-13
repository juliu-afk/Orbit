import { createRouter, createWebHashHistory } from 'vue-router'
import { usePreFlightStore } from '@/stores/preflight'

const router = createRouter({
  history: createWebHashHistory(),
  routes: [
    { path: '/', redirect: '/boot' },
    { path: '/boot', name: 'boot', component: () => import('@/views/BootView.vue') },
    // WHY 去 requiresProbe: boot.html 已独立验证后端可用，直接进 /app 避免二次预检
    { path: '/app', name: 'app', component: () => import('@/views/TerminalShell.vue') },
    { path: '/mcp', name: 'mcp', component: () => import('@/views/McpView.vue') },
    { path: '/review/:taskId', name: 'review', component: () => import('@/views/ReviewView.vue') },
    { path: '/skills', name: 'skills', component: () => import('@/views/SkillManager.vue') },
  ],
})

router.beforeEach((to, _from, next) => {
  const preflight = usePreFlightStore()
  if (to.name === 'boot') {
    if (preflight.status === 'passed') return next({ name: 'app' })
    return next()
  }
  if (to.meta?.requiresProbe && preflight.status !== 'passed') return next({ name: 'boot' })
  next()
})

export default router
