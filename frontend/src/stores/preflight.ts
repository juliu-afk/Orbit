/** PreFlight Store——启动预检状态管理。
 *
 * 轮询 /api/v1/observability/startup-probe，追踪 8 项检查进度。
 * 含自愈统计、失败检测、重试逻辑。
 */
import { defineStore } from 'pinia'
import { ref, computed } from 'vue'

export type CheckStatus = 'pending' | 'running' | 'passed' | 'failed' | 'skipped' | 'repaired'
export type PreFlightStatus = 'booting' | 'running' | 'passed' | 'failed'

export interface PreFlightCheck {
  name: string
  label: string
  status: CheckStatus
  message: string
  auto_repaired: boolean
  duration_ms: number
}

const PROBE_URL = '/api/v1/observability/startup-probe'
const POLL_MS = 1500

export const usePreFlightStore = defineStore('preflight', () => {
  const status = ref<PreFlightStatus>('booting')
  const checks = ref<PreFlightCheck[]>([])
  const autoRepairs = ref(0)
  const errorMessage = ref('')
  const elapsedMs = ref(0)

  let pollTimer: ReturnType<typeof setInterval> | null = null

  // ── Computed ──

  const progress = computed(() => {
    if (checks.value.length === 0) return status.value === 'booting' ? 5 : 0
    const done = checks.value.filter(
      c => c.status === 'passed' || c.status === 'repaired' || c.status === 'skipped' || c.status === 'failed'
    ).length
    return Math.round((done / checks.value.length) * 100)
  })

  const hasFailed = computed(() =>
    checks.value.some(c => c.status === 'failed')
  )

  const repairedItems = computed(() =>
    checks.value.filter(c => c.auto_repaired)
  )

  // ── Actions ──

  async function poll() {
    try {
      const r = await fetch(PROBE_URL)
      if (!r.ok) throw new Error(`HTTP ${r.status}`)
      const j = await r.json()
      if (j.code !== 0) throw new Error(j.message)

      const data = j.data
      status.value = (data.status as PreFlightStatus) || 'booting'
      checks.value = (data.checks || []) as PreFlightCheck[]
      autoRepairs.value = data.auto_repairs || 0
      elapsedMs.value = data.elapsed_ms || 0

      if (data.status === 'passed') {
        stopPolling()
        status.value = 'passed'
      }
      if (data.status === 'failed') {
        stopPolling()
        status.value = 'failed'
        // 只显示真正失败（不可自愈）的项
        const failed = checks.value.filter(c => c.status === 'failed')
        if (failed.length > 0) {
          errorMessage.value = failed.map(f => `${f.label}: ${f.message}`).join('；')
        }
      }
    } catch {
      // 后端未就绪——静默等下一轮
      if (status.value !== 'running') {
        status.value = 'booting'
      }
    }
  }

  function startPolling() {
    if (pollTimer) return
    poll() // 立即首轮
    pollTimer = setInterval(poll, POLL_MS)
  }

  function stopPolling() {
    if (pollTimer) {
      clearInterval(pollTimer)
      pollTimer = null
    }
  }

  async function retry() {
    stopPolling()
    status.value = 'booting'
    errorMessage.value = ''
    try {
      await fetch(`${PROBE_URL}/reset`, { method: 'POST' })
    } catch {
      // 静默
    }
    startPolling()
  }

  function reset() {
    stopPolling()
    status.value = 'booting'
    checks.value = []
    autoRepairs.value = 0
    errorMessage.value = ''
    elapsedMs.value = 0
  }

  return {
    status, checks, autoRepairs, errorMessage, elapsedMs,
    progress, hasFailed, repairedItems,
    startPolling, stopPolling, retry, reset,
  }
})
