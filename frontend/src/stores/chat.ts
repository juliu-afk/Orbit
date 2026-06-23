/** Chat Store——NL 聊天状态管理。
 *
 * 管理消息历史/匹配候选/会话项目列表。
 * WebSocket 连接由 useWebSocket composable + DashboardView 统一管理，
 * Store 只负责状态和 send/receive 逻辑。
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
}

export const useChatStore = defineStore('chat', () => {
  const messages = ref<ChatMessage[]>([])
  const candidates = ref<Candidate[]>([])
  const sessionProjects = ref<string[]>([])
  const keywords = ref<string[]>([])
  const matchSource = ref<string>('')
  const requiresConfirmation = ref(true)
  const connecting = ref(false)

  // WS 实例——由外部注入（DashboardView 传入）
  let wsInstance: WebSocket | null = null

  function setWs(ws: WebSocket) {
    wsInstance = ws
  }

  /** 发送文本——通过 WS 推送到后端 /api/v1/chat */
  function send(text: string) {
    if (!text.trim()) return

    // 追加用户消息
    const userMsg: ChatMessage = {
      id: `u-${Date.now()}`,
      text: text.trim(),
      from: 'user',
      timestamp: Date.now(),
    }
    messages.value.push(userMsg)

    // 通过 WS 发送
    if (wsInstance && wsInstance.readyState === WebSocket.OPEN) {
      wsInstance.send(JSON.stringify({
        type: 'chat',
        text: userMsg.text,
        session_projects: sessionProjects.value,
      }))
    }
    // 清理旧消息（保留最近 50 条）
    if (messages.value.length > 50) {
      messages.value = messages.value.slice(-50)
    }
  }

  /** 处理服务端响应——更新候选列表 */
  function handleResponse(data: MatchData) {
    keywords.value = data.keywords
    candidates.value = data.candidates
    matchSource.value = data.source
    requiresConfirmation.value = data.requires_confirmation

    // 追加系统消息
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

  /** 确认项目——加入会话历史 */
  function confirm(projectName: string) {
    if (!sessionProjects.value.includes(projectName)) {
      sessionProjects.value.push(projectName)
    }
    // 确认后清空候选
    candidates.value = []
  }

  /** 切换会话项目 */
  function switchProject(projectName: string) {
    sessionProjects.value = sessionProjects.value.filter(p => p !== projectName)
    if (!sessionProjects.value.includes(projectName)) {
      sessionProjects.value.push(projectName)
    }
  }

  function reset() {
    messages.value = []
    candidates.value = []
    sessionProjects.value = []
    keywords.value = []
    matchSource.value = ''
    requiresConfirmation.value = true
  }

  return {
    messages, candidates, sessionProjects, keywords, matchSource,
    requiresConfirmation, connecting,
    setWs, send, handleResponse, confirm, switchProject, reset,
  }
})
