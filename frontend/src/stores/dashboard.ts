/** 驾驶舱全局状态。
 *
 * 管理当前订阅任务和最后更新时间。
 * WS 连接状态由 useWebSocket composable 管理，不在此 Store。
 */
import { defineStore } from 'pinia'
import { ref } from 'vue'

export const useDashboardStore = defineStore('dashboard', () => {
  const currentTaskId = ref<string | null>(null)
  const lastUpdateTime = ref<number | null>(null)

  function setTask(taskId: string) {
    currentTaskId.value = taskId
  }

  function clearTask() {
    currentTaskId.value = null
    lastUpdateTime.value = null
  }

  function touch() {
    lastUpdateTime.value = Date.now()
  }

  return { currentTaskId, lastUpdateTime, setTask, clearTask, touch }
})
