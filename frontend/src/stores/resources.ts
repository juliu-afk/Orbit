/** Resources Store——资源调度/队列/工具数据管理。 */
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

export const useResourcesStore = defineStore('resources', () => {
  const queueStatus = ref<QueueStatus>({ critical: 0, high: 0, normal: 0, low: 0, active: 0 })
  const toolStats = ref<ToolStat[]>([])
  const loading = ref(false)

  async function fetchQueue() {
    // 占位：后续 GET /api/v1/scheduler/queue-status
    queueStatus.value = { critical: 0, high: 0, normal: 0, low: 0, active: 0 }
  }

  async function fetchTools() {
    // 占位：后续 GET /api/v1/tools/stats
    toolStats.value = []
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
