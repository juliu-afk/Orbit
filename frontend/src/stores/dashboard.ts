/** 驾驶舱全局状态（精简版——Session PR #3）。
 *
 * 仅管理 WS 连接状态。任务/指标/Session 由各自 Store 管理。
 */
import { defineStore } from 'pinia'
import { ref } from 'vue'

export const useDashboardStore = defineStore('dashboard', () => {
  const wsStatus = ref<'connected' | 'connecting' | 'disconnected'>('disconnected')

  function setWsStatus(s: 'connected' | 'connecting' | 'disconnected') {
    wsStatus.value = s
  }

  return { wsStatus, setWsStatus }
})
