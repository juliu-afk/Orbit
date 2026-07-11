/** Loop Store（PR4）——定时任务（Cron-like）管理。
 *
 * 对应后端 /api/v1/loop/* 路由。定时重复执行 shell 命令。
 */
import { defineStore } from 'pinia'
import { ref } from 'vue'
import { apiGet, apiPost, apiDelete } from '@/services/api'

export interface LoopTask {
  id: string
  interval_seconds: number
  command: string
  status: string
  run_count: number
}

export const useLoopStore = defineStore('loop', () => {
  const loops = ref<LoopTask[]>([])
  const loading = ref(false)
  const error = ref('')

  async function fetchLoops() {
    loading.value = true
    error.value = ''
    try {
      const data = await apiGet<{ loops: LoopTask[]; total: number }>('/api/v1/loop')
      loops.value = data.loops || []
    } catch {
      error.value = '加载定时任务失败'
      loops.value = []
    } finally {
      loading.value = false
    }
  }

  async function createLoop(interval: string, command: string) {
    await apiPost('/api/v1/loop', { interval, command })
    await fetchLoops()
  }

  async function stopLoop(id: string) {
    await apiDelete(`/api/v1/loop/${id}`)
    await fetchLoops()
  }

  async function pauseLoop(id: string) {
    await apiPost(`/api/v1/loop/${id}/pause`, {})
    await fetchLoops()
  }

  async function resumeLoop(id: string) {
    await apiPost(`/api/v1/loop/${id}/resume`, {})
    await fetchLoops()
  }

  return { loops, loading, error, fetchLoops, createLoop, stopLoop, pauseLoop, resumeLoop }
})
