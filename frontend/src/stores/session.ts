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
    // WHY: 空会话自动清理——切换走无消息的会话时自动归档，不残留空标签
    const prevId = currentSessionId.value
    const prevMsgCount = messages.value.length
    if (prevId && prevId !== sessionId && prevMsgCount === 0) {
      archiveSession(prevId)  // 不 await——后台清理，不阻塞切换
    }

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

  // WHY: 右键关闭任意 session——不限于当前 session
  async function archiveSession(sessionId: string) {
    await fetch(`${SESSIONS_URL}/${sessionId}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ status: 'archived' }),
    })
    // 从本地列表移除
    sessions.value = sessions.value.filter(s => s.session_id !== sessionId)
    // 如果关闭的是当前 session，清空当前并自动切到第一个剩余 session
    if (currentSessionId.value === sessionId) {
      clearCurrent()
      if (sessions.value.length > 0) {
        await switchToSession(sessions.value[0].session_id)
      }
    }
  }

  // WHY: 会话智能标题——首条用户消息到达后持久化标题到后台
  async function updateTitle(sessionId: string, title: string) {
    try {
      await fetch(`${SESSIONS_URL}/${sessionId}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ title }),
      })
      // 同步本地 sessions 列表中的 title
      const idx = sessions.value.findIndex(s => s.session_id === sessionId)
      if (idx >= 0) sessions.value[idx] = { ...sessions.value[idx], title }
      if (currentSessionId.value === sessionId) currentTitle.value = title
    } catch { /* 静默 */ }
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

  // ── UX #13: 对话分支 ──
  const childSessions = ref<SessionSummary[]>([])

  async function forkSession(messageIndex?: number): Promise<string | null> {
    if (!currentSessionId.value) return null
    try {
      const body: Record<string, unknown> = {}
      if (messageIndex !== undefined) body.fork_at_message_index = messageIndex
      const r = await fetch(`${SESSIONS_URL}/${currentSessionId.value}/fork`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      })
      const j = await r.json()
      if (j.code !== 0) throw new Error(j.message || 'fork failed')
      const child = j.data as SessionSummary
      childSessions.value.unshift(child)
      return child.session_id
    } catch {
      return null
    }
  }

  async function fetchChildSessions() {
    if (!currentSessionId.value) return
    try {
      const r = await fetch(`${SESSIONS_URL}/${currentSessionId.value}/forks`)
      const j = await r.json()
      if (j.code === 0) childSessions.value = j.data as SessionSummary[]
    } catch {
      // 静默
    }
  }

  function reset() {
    clearCurrent()
    sessions.value = []
    childSessions.value = []
  }

  return {
    currentSessionId, currentProjectName, currentProjectPath, currentTitle,
    sessions, messages, loading, childSessions,
    fetchSessions, createSession, switchToSession, archiveCurrentSession,
    archiveSession, updateTitle, clearCurrent, getMetricsFilter, forkSession, fetchChildSessions, reset,
  }
})
