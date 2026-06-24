/** Chat Store——NL 聊天状态管理。
 *
 * 管理消息历史/匹配候选/跨项目警告。
 * Session PR #3: 移除 sessionProjects, 加 session_id/project_name 上送,
 *   消息持久化转移到 sessionStore.
 */
import { defineStore } from 'pinia'
import { ref } from 'vue'

export interface ChatMessage {
  id: string
  text: string
  from: 'user' | 'system'
  timestamp: number
}

export interface Candidate {
  project: string
  score: number
  reason: string
  matched_keywords: string[]
}

export interface MatchData {
  query: string
  keywords: string[]
  candidates: Candidate[]
  source: string
  requires_confirmation: boolean
  cross_project_warning?: string | null
}

export const useChatStore = defineStore('chat', () => {
  const messages = ref<ChatMessage[]>([])
  const candidates = ref<Candidate[]>([])
  const keywords = ref<string[]>([])
  const matchSource = ref<string>('')
  const requiresConfirmation = ref(true)
  const connecting = ref(false)
  const crossProjectWarning = ref<string | null>(null)  // Session PR #3

  // WS 实例——由外部注入（DashboardView 传入）
  let wsInstance: WebSocket | null = null

  function setWs(ws: WebSocket) {
    wsInstance = ws
  }

  /** 发送文本——附 session_id + project_name */
  function send(text: string, sessionId: string, projectName: string) {
    if (!text.trim()) return

    const userMsg: ChatMessage = {
      id: `u-${Date.now()}`,
      text: text.trim(),
      from: 'user',
      timestamp: Date.now(),
    }
    messages.value.push(userMsg)

    if (wsInstance && wsInstance.readyState === WebSocket.OPEN) {
      wsInstance.send(JSON.stringify({
        type: 'chat',
        text: userMsg.text,
        session_id: sessionId,
        project_name: projectName,
      }))
    }
    if (messages.value.length > 50) {
      messages.value = messages.value.slice(-50)
    }
  }

  /** 处理服务端响应 */
  function handleResponse(data: MatchData) {
    keywords.value = data.keywords
    candidates.value = data.candidates
    matchSource.value = data.source
    requiresConfirmation.value = data.requires_confirmation

    // Session PR #3: 跨项目警告
    if (data.cross_project_warning) {
      crossProjectWarning.value = data.cross_project_warning
    }

    const sysMsg: ChatMessage = {
      id: `s-${Date.now()}`,
      text: candidates.value.length > 0
        ? `匹配到 ${candidates.value.length} 个项目`
        : '未找到匹配项目',
      from: 'system',
      timestamp: Date.now(),
    }
    messages.value.push(sysMsg)
  }

  /** 确认项目——清空候选列表 */
  function confirm(_projectName?: string) {
    candidates.value = []
  }

  /** 解除跨项目警告 */
  function dismissWarning() {
    crossProjectWarning.value = null
  }

  /** 恢复聊天消息（从 sessionStore 加载） */
  function restoreMessages(msgs: Array<{ role: string; content: string; created_at: number }>) {
    messages.value = msgs.map((m, i) => ({
      id: `r-${i}`,
      text: m.content,
      from: m.role === 'user' ? 'user' : 'system',
      timestamp: m.created_at * 1000,
    }))
  }

  function reset() {
    messages.value = []
    candidates.value = []
    keywords.value = []
    matchSource.value = ''
    requiresConfirmation.value = true
    crossProjectWarning.value = null
  }

  return {
    messages, candidates, keywords, matchSource,
    requiresConfirmation, connecting, crossProjectWarning,
    setWs, send, handleResponse, confirm, dismissWarning,
    restoreMessages, reset,
  }
})
