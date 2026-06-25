/** Resources Store??????/???????? observability metrics?? */
import { defineStore } from 'pinia'
import { ref } from 'vue'

export interface QueueStatus {
  critical: number
  high: number
  normal: number
  low: number
  active: number
}

export interface ToolStat {
  tool_name: string
  count: number
  last_used: number
  rate_limited: boolean
}

const METRICS_URL = '/api/v1/observability/metrics'

export const useResourcesStore = defineStore('resources', () => {
  const queueStatus = ref<QueueStatus>({ critical: 0, high: 0, normal: 0, low: 0, active: 0 })
  const toolStats = ref<ToolStat[]>([])
  const loading = ref(false)

  async function fetchQueue() {
    try {
      const r = await fetch(METRICS_URL)
      const j = await r.json()
      if (j.code === 0 && j.data) {
        queueStatus.value = {
          ...queueStatus.value,
          active: j.data.active_tasks ?? 0,
        }
      }
    } catch {
    }
  }

  async function fetchTools() {
    try {
      const r = await fetch(METRICS_URL)
      const j = await r.json()
      if (j.code === 0 && j.data?.sandbox_executions_total) {
        const execs = j.data.sandbox_executions_total
        toolStats.value = [
          {
            tool_name: 'sandbox',
            count: (execs.success ?? 0) + (execs.failed ?? 0),
            last_used: 0,
            rate_limited: false,
          },
        ]
      }
    } catch {
    }
  }

  async function fetchAll() {
    loading.value = true
    await Promise.all([fetchQueue(), fetchTools()])
    loading.value = false
  }

  function reset() {
    queueStatus.value = { critical: 0, high: 0, normal: 0, low: 0, active: 0 }
    toolStats.value = []
  }

  return { queueStatus, toolStats, loading, fetchAll, reset }
})
