/** Session Store——会话管理 + 消息恢复。
 *
 * Session = 项目绑定的工作上下文。
 * 管理: Session 列表/切换/创建、聊天消息持久化。
 */
import { defineStore } from 'pinia'
import { ref } from 'vue'

export interface SessionSummary {
  session_id: string
  project_name: string
  local_path: string
  title: string
  status: 'active' | 'archived'
  created_at: number
  updated_at: number
}

export interface StoredMessage {
  id: number
  session_id: string
  role: 'user' | 'system' | 'agent'
  content: string
  candidates: Array<{
    project: string
    score: number
    reason: string
    matched_keywords: string[]
  }>
  cross_project_warning: string | null
  created_at: number
}

const SESSIONS_URL = '/api/v1/sessions'

export const useSessionStore = defineStore('session', () => {
  const currentSessionId = ref<string | null>(null)
  const currentProjectName = ref<string>('')
  const currentProjectPath = ref<string>('')
  const currentTitle = ref<string>('')
  const sessions = ref<SessionSummary[]>([])
  const messages = ref<StoredMessage[]>([])
  const loading = ref(false)

  // ── Actions ──

  async function fetchSessions() {
    try {
      const r = await fetch(`${SESSIONS_URL}?status_filter=active`)
      const j = await r.json()
      if (j.code === 0) {
        sessions.value = j.data as SessionSummary[]
      }
    } catch {
      // 静默
    }
  }

  async function createSession(projectName: string, title?: string): Promise<string> {
    const r = await fetch(SESSIONS_URL, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ project_name: projectName, title: title || '' }),
    })
    const j = await r.json()
    if (j.code !== 0) throw new Error(j.message || '创建会话失败')
    const s = j.data as SessionSummary
    sessions.value.unshift(s)
    await switchToSession(s.session_id)
    return s.session_id
  }

  async function switchToSession(sessionId: string) {
    loading.value = true
    try {
      const r = await fetch(`${SESSIONS_URL}/${sessionId}`)
      const j = await r.json()
      if (j.code !== 0) throw new Error(j.message)

      const detail = j.data as { session: SessionSummary; messages: StoredMessage[] }
      currentSessionId.value = detail.session.session_id
      currentProjectName.value = detail.session.project_name
      currentProjectPath.value = detail.session.local_path || ''
      currentTitle.value = detail.session.title
      messages.value = detail.messages || []
    } catch {
      // 静默
    } finally {
      loading.value = false
    }
  }

  async function archiveCurrentSession() {
    if (!currentSessionId.value) return
    await fetch(`${SESSIONS_URL}/${currentSessionId.value}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ status: 'archived' }),
    })
    clearCurrent()
    await fetchSessions()
  }

  function clearCurrent() {
    currentSessionId.value = null
    currentProjectName.value = ''
    currentTitle.value = ''
    messages.value = []
  }

  function getMetricsFilter(): { session_id: string } | Record<string, never> {
    return currentSessionId.value ? { session_id: currentSessionId.value } : {}
  }

  function reset() {
    clearCurrent()
    sessions.value = []
  }

  return {
    currentSessionId, currentProjectName, currentProjectPath, currentTitle,
    sessions, messages, loading,
    fetchSessions, createSession, switchToSession, archiveCurrentSession,
    clearCurrent, getMetricsFilter, reset,
  }
})
