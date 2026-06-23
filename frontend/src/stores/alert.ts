/** 告警列表状态。
 *
 * 消费 WebSocket 'alert:new' 事件，维护最近 20 条。
 */
import { defineStore } from 'pinia'
import { ref } from 'vue'
import type { Alert } from '@/types/dashboard'

const MAX_ALERTS = 20

export const useAlertStore = defineStore('alert', () => {
  const alerts = ref<Alert[]>([])

  function addAlert(alert: Alert) {
    alerts.value.unshift(alert)
    if (alerts.value.length > MAX_ALERTS) {
      alerts.value.pop()
    }
  }

  function clearAlerts() {
    alerts.value = []
  }

  return { alerts, addAlert, clearAlerts }
})
