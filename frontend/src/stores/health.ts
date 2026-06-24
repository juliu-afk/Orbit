/** Health Store??????????
 *
 * ??? /api/v1/observability/health/{component} ???
 */
import { defineStore } from 'pinia'
import { ref } from 'vue'

const HEALTH_URL = '/api/v1/observability/health'

export interface ComponentHealthDetail {
  name: string
  status: 'healthy' | 'degraded' | 'unhealthy' | 'unknown'
  message: string
  metrics: Record<string, unknown>
}

export const useHealthStore = defineStore('health', () => {
  const componentDetail = ref<ComponentHealthDetail | null>(null)
  const loading = ref(false)

  /** ????????? */
  async function fetchComponent(component: string) {
    loading.value = true
    try {
      const r = await fetch(`${HEALTH_URL}/${component}`)
      const j = await r.json()
      componentDetail.value = j
    } catch {
      // ??
    } finally {
      loading.value = false
    }
  }

  function reset() {
    componentDetail.value = null
  }

  return { componentDetail, loading, fetchComponent, reset }
})
