import { createRouter, createWebHashHistory } from 'vue-router'
import { usePreFlightStore } from '@/stores/preflight'

const router = createRouter({
  history: createWebHashHistory(),
  routes: [
    { path: '/', redirect: '/boot' },
    { path: '/boot', name: 'boot', component: () => import('@/views/BootView.vue') },
    { path: '/app', name: 'app', component: () => import('@/views/TerminalShell.vue'), meta: { requiresProbe: true } },
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
