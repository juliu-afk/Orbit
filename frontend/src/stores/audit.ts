/** Audit Store - audit logs and lessons.
 *
 */
import { defineStore } from 'pinia'
import { ref } from 'vue'

const OBSERVABILITY_URL = '/api/v1/observability'

export interface AuditEntry {
  lesson_id: string
  task_id: string
  domain: string
  outcome: string
  lesson: string
  tags: string[]
}

export interface LessonEntry {
  lesson_id: string
  task_id: string
  domain: string
  outcome: string
  lesson: string
}

export const useAuditStore = defineStore('audit', () => {
  const auditLogs = ref<AuditEntry[]>([])
  const lessons = ref<LessonEntry[]>([])
  const loading = ref(false)
  const error = ref<string | null>(null)

  /** Fetch audit logs by task_id. */
  async function fetchAudit(taskId: string) {
    loading.value = true
    try {
      const r = await fetch(`${OBSERVABILITY_URL}/audit?task_id=${encodeURIComponent(taskId)}`)
      const j = await r.json()
      if (j.code === 0) {
        auditLogs.value = j.data || []
      }
    } catch (e) {
      console.warn("[audit] request failed", e)
    } finally {
      loading.value = false
    }
  }

  async function fetchLessons() {
    loading.value = true
    try {
      const r = await fetch(`${OBSERVABILITY_URL}/lessons`)
      const j = await r.json()
      if (j.code === 0) {
        lessons.value = j.data || []
      }
    } catch (e) {
      console.warn("[audit] request failed", e)
    } finally {
      loading.value = false
    }
  }

  async function recordLesson(data: {
    task_id: string
    domain: string
    outcome: string
    lesson: string
  }) {
    try {
      await fetch(`${OBSERVABILITY_URL}/lessons`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data),
      })
    } catch (e) {
      console.warn("[audit] request failed", e)
    }
  }

  function reset() {
    auditLogs.value = []
    lessons.value = []
    error.value = null
  }

  return { auditLogs, lessons, loading, error, fetchAudit, fetchLessons, recordLesson, reset }
})
