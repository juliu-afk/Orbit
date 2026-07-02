/** 高峰避让调度 Store。 */
import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { apiGet } from '@/services/api'

export interface PeakStatusData {
  is_peak: boolean
  providers: Record<string, { is_peak: boolean; peak_ends_at: string | null; next_offpeak: { starts_at: string | null; ends_at: string | null } | null }>
  queue_summary: { total_queued: number; by_provider: Record<string, number> }
}

export interface DeferredTaskItem { goal_id: string; description: string; priority: string; provider: string; target_window_start: string; estimated_duration_seconds: number; status: string }

export interface PeakPromptData { goal_id: string; provider: string; next_offpeak: string; prompt: string }

export interface SavingsReport { total_tasks_deferred: number; total_tasks_done: number; total_tasks_queued: number; total_tokens_offpeak: number; total_saved_yuan: number; by_provider: Array<{ provider: string; tasks: number; tokens: number; saved_yuan: number }> }

export const usePeakStore = defineStore('peak', () => {
  const status = ref<PeakStatusData | null>(null)
  const queued = ref<DeferredTaskItem[]>([])
  const savings = ref<SavingsReport | null>(null)

  const isPeak = computed(() => status.value?.is_peak ?? false)
  const queuedCount = computed(() => status.value?.queue_summary?.total_queued ?? 0)

  async function fetchPeakStatus() {
    try { status.value = await apiGet<PeakStatusData>('/api/v1/schedule/peak-status') } catch { /* 非关键 */ }
  }
  async function fetchQueue() {
    try { const d = await apiGet<{ queued: DeferredTaskItem[]; count: number }>('/api/v1/schedule/queue'); queued.value = d.queued } catch { /* */ }
  }
  async function fetchSavings() {
    try { savings.value = await apiGet<SavingsReport>('/api/v1/schedule/savings-report') } catch { /* */ }
  }
  async function promoteToUrgent(goalId: string) {
    try {
    await fetch(`/api/v1/schedule/queue/${goalId}/urgent`, { method: 'POST' })
    await fetchQueue(); await fetchPeakStatus()
    } catch (e) { console.error("[peak] promoteToUrgent failed:", e) }
  }
  async function refreshAll() {
    await Promise.all([fetchPeakStatus(), fetchQueue(), fetchSavings()])
  }
  return { status, queued, savings, isPeak, queuedCount, fetchPeakStatus, fetchQueue, fetchSavings, promoteToUrgent, refreshAll }
})
