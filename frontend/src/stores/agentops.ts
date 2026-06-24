/** AgentOps Store——指标/告警/健康数据集中管理。
 *
 * 双通道更新：WebSocket 推送 (实时) + HTTP 轮询 (5s 兜底)。
 * Session PR #3: 加 session_id 过滤参数。
 */
import { defineStore } from 'pinia'
import { ref } from 'vue'
import type { AgentOpsAlert, ComponentHealth, MetricsSnapshot } from '@/types/dashboard'
import { useSessionStore } from '@/stores/session'

const POLL_INTERVAL_MS = 5000
const METRICS_URL = '/api/v1/observability/metrics'
const ALERTS_URL = '/api/v1/observability/alerts'
const HEALTH_URL = '/api/v1/observability/health'

export const useAgentOpsStore = defineStore('agentops', () => {
  const metrics = ref<MetricsSnapshot | null>(null)
  const alerts = ref<AgentOpsAlert[]>([])
  const health = ref<ComponentHealth[]>([])
  const overallHealth = ref<string>('unknown')
  const lastUpdated = ref<number | null>(null)
  const loading = ref(false)

  let pollTimer: ReturnType<typeof setInterval> | null = null

  // ── HTTP 轮询 (兜底) ────────────────────────────

  function _buildUrl(base: string): string {
    // Session PR #3: 按 current session 过滤
    const sessionStore = useSessionStore()
    const sid = sessionStore.currentSessionId
    return sid ? `${base}?session_id=${sid}` : base
  }

  async function fetchMetrics() {
    try {
      const r = await fetch(_buildUrl(METRICS_URL))
      const j = await r.json()
      if (j.code === 0) {
        metrics.value = j.data as MetricsSnapshot
        lastUpdated.value = Date.now()
      }
    } catch {
      // 静默失败——保持上一份数据
    }
  }

  async function fetchAlerts() {
    try {
      const r = await fetch(_buildUrl(ALERTS_URL))
      const j = await r.json()
      if (j.code === 0) {
        alerts.value = (j.data || []) as AgentOpsAlert[]
      }
    } catch {
      // 静默失败
    }
  }

  async function fetchHealth() {
    try {
      const r = await fetch(HEALTH_URL)
      const j = await r.json()
      if (j.components) {
        health.value = j.components as ComponentHealth[]
        overallHealth.value = j.overall as string
      }
    } catch {
      // 静默失败
    }
  }

  async function fetchAll() {
    loading.value = true
    await Promise.all([fetchMetrics(), fetchAlerts(), fetchHealth()])
    loading.value = false
  }

  // ── WebSocket 事件处理 ──────────────────────────

  function handleWsEvent(type: string, payload: Record<string, unknown>) {
    switch (type) {
      case 'metrics:snapshot':
        metrics.value = payload as unknown as MetricsSnapshot
        lastUpdated.value = Date.now()
        break
      case 'agentops:alert':
      case 'alert:new':
        // 追加告警（WS 推送的告警）
        if (payload.alert_name) {
          alerts.value.push(payload as unknown as AgentOpsAlert)
        }
        break
    }
  }

  // ── 生命周期 ────────────────────────────────────

  function startPolling() {
    if (pollTimer) return
    fetchAll()
    pollTimer = setInterval(fetchAll, POLL_INTERVAL_MS)
  }

  function stopPolling() {
    if (pollTimer) {
      clearInterval(pollTimer)
      pollTimer = null
    }
  }

  function reset() {
    stopPolling()
    metrics.value = null
    alerts.value = []
    health.value = []
    overallHealth.value = 'unknown'
  }

  return {
    metrics, alerts, health, overallHealth, lastUpdated, loading,
    fetchAll, startPolling, stopPolling, reset, handleWsEvent,
  }
})
