/** Chat Store——NL 聊天状态管理 + Agent 验收交互
 *
 * 管理消息/候选/结构化 PRD/任务状态。
 * 对接后端 /api/v1/chat，ClarifierAgent 处理需求澄清和 LLM 调用。
 */
import { defineStore } from 'pinia'
import { ref } from 'vue'
import type { PeakPromptData } from '@/stores/peak'

export interface ChatMessage {
  id: string
  text: string
  from: 'user' | 'agent' | 'system'
  timestamp: number
  role?: string  // Agent 角色名（Clarifier/Developer/Reviewer等）
}

export interface Candidate {
  project: string
  score: number
  reason: string
  matched_keywords: string[]
}

export interface StructuredPRD {
  goal: string
  scope: string
  acceptance_criteria: string[]
  edge_cases?: string[]
  constraints?: string[]
  acceptance_options?: string[]
}

export interface ClarifyResponse {
  type: 'clarify' | 'task_created' | 'peak_prompt'
  reply: string
  clarification_status: 'clarifying' | 'ready'
  structured_prd: StructuredPRD | null
  missing_fields: string[]
  candidates?: Candidate[]
  agent_role?: string  // 当前回复的 Agent 角色名
  // task_created 时
  task_id?: string
  state?: string
}

export const useChatStore = defineStore('chat', () => {
  const messages = ref<ChatMessage[]>([])
  const candidates = ref<Candidate[]>([])
  const clarificationStatus = ref<'clarifying' | 'ready'>('clarifying')
  const structuredPrd = ref<StructuredPRD | null>(null)
  const missingFields = ref<string[]>([])
  const connecting = ref(false)
  const crossProjectWarning = ref<string | null>(null)
  const lastTaskId = ref<string | null>(null)
  const lastPeakPrompt = ref<PeakPromptData | null>(null)
  const pendingGoalText = ref('')
  const lastError = ref<string | null>(null)

  // chat WS 连接到 /api/v1/chat（非 /ws/dashboard）
  let chatWs: WebSocket | null = null
  let reconnectTimer: ReturnType<typeof setTimeout> | null = null

  /** 建立 chat WebSocket 连接到 /api/v1/chat 端点，失败自动重试最多 5 次 */
  function connectChatWs(_sessionId: string, _projectName: string) {
    disconnect()

    const protocol = location.protocol === 'https:' ? 'wss:' : 'ws:'
    // P0-1: WS 认证——附加 token 查询参数，桌面应用无 token 时后端 AUTH_ENABLED=False 跳过校验
    const token = localStorage.getItem('orbitAuthToken') || ''
    const url = `${protocol}//${location.host}/api/v1/chat${token ? `?token=${encodeURIComponent(token)}` : ''}`
    let retries = 0
    const MAX_RETRIES = 5

    function doConnect() {
      connecting.value = true
      chatWs = new WebSocket(url)

      chatWs.onopen = () => {
        connecting.value = false
        lastError.value = null
        retries = 0
      }

      chatWs.onmessage = (event: MessageEvent) => {
        try {
          const resp = JSON.parse(event.data as string)
          handleChatResponse(resp)
        } catch {
          if (import.meta.env.DEV) console.warn('[chat] 消息解析失败', event.data)
        }
      }

      chatWs.onclose = () => {
        connecting.value = false
        chatWs = null
      }

      chatWs.onerror = () => {
        connecting.value = false
        chatWs = null
        retries++
        if (retries <= MAX_RETRIES) {
          const delay = Math.min(1000 * Math.pow(2, retries - 1), 16000)
          reconnectTimer = setTimeout(doConnect, delay)
        } else {
          lastError.value = '连接失败'
        }
      }
    }

    doConnect()
  }

  /** 处理后端 chat 响应 {code, data, message} 格式 */
  function handleChatResponse(resp: { code: number; data: ClarifyResponse; message: string }) {
    if (resp.code !== 0) {
      lastError.value = resp.message
      // 错误消息也加入聊天记录
      messages.value.push({
        id: `e-${Date.now()}`,
        text: resp.message,
        from: 'system',
        timestamp: Date.now(),
      })
      return
    }
    lastError.value = null
    const data = resp.data

    if (data.type === 'peak_prompt') { lastPeakPrompt.value = data as unknown as PeakPromptData; return }
      if (data.type === 'task_created') {
      // 任务已创建
      lastTaskId.value = data.task_id ?? null
      messages.value.push({
        id: `t-${Date.now()}`,
        text: data.reply ?? `任务已创建：${data.task_id}`,
        from: 'system',
        timestamp: Date.now(),
      })
      return
    }

    // clarify 状态
    clarificationStatus.value = data.clarification_status
    structuredPrd.value = data.structured_prd
    missingFields.value = data.missing_fields || []
    if (data.candidates) {
      candidates.value = data.candidates
    }

    // Agent 回复加入消息列表（含角色名）
    messages.value.push({
      id: `a-${Date.now()}`,
      text: data.reply,
      from: 'agent',
      timestamp: Date.now(),
      role: data.agent_role || undefined,
    })
    if (messages.value.length > 50) {
      messages.value = messages.value.slice(-50)
    }
  }

  /** 发送消息 */
  function send(text: string, sessionId: string, projectName: string) {
    if (!text.trim()) return
    pendingGoalText.value = text.trim()
    if (!chatWs || chatWs.readyState !== WebSocket.OPEN) {
      lastError.value = '未连接到聊天服务'
      return
    }

    messages.value.push({
      id: `u-${Date.now()}`,
      text: text.trim(),
      from: 'user',
      timestamp: Date.now(),
    })

    chatWs.send(JSON.stringify({
      type: 'chat',
      text: text.trim(),
      session_id: sessionId,
      project_name: projectName,
    }))
  }

  /** 确认 PRD 并提交任务 */
  function confirmPrd(sessionId: string, projectName: string, modifiedPrd?: StructuredPRD) {
    if (!chatWs || chatWs.readyState !== WebSocket.OPEN) {
      lastError.value = '未连接'
      return
    }

    const payload: Record<string, unknown> = {
      type: 'confirm',
      session_id: sessionId,
      project_name: projectName,
    }
    // 如果提供了 modified_prd 则使用，否则用 store 中的 prd
    if (modifiedPrd) {
      payload.modified_prd = modifiedPrd
    } else if (structuredPrd.value) {
      payload.modified_prd = structuredPrd.value
    }

    chatWs.send(JSON.stringify(payload))
  }

  /** 清空候选列表 */
  function confirm(_projectName?: string) {
    candidates.value = []
  }

  /** 解除跨项目警告 */
  function dismissWarning() {
    crossProjectWarning.value = null
  }

  /** 关闭 chat WS，取消重试 */
  function disconnect() {
    if (reconnectTimer) {
      clearTimeout(reconnectTimer)
      reconnectTimer = null
    }
    if (chatWs) {
      chatWs.close()
      chatWs = null
    }
    connecting.value = false
  }

  /** 恢复聊天消息（从 sessionStore 加载） */
  function restoreMessages(msgs: Array<{ role: string; content: string; created_at: number }>) {
    messages.value = msgs.map((m, i) => ({
      id: `r-${i}`,
      text: m.content,
      from: m.role === 'user' ? 'user' : 'agent',
      timestamp: m.created_at * 1000,
    }))
  }

  function resubmitWithDefer() { lastPeakPrompt.value = null; return fetch('/api/v1/goal',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({description:pendingGoalText.value,defer_to_offpeak:true})}) }
  function resubmitWithUrgent() { lastPeakPrompt.value = null; return fetch('/api/v1/goal',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({description:pendingGoalText.value,urgent:true})}) }
  function reset() {
    messages.value = []
    candidates.value = []
    clarificationStatus.value = 'clarifying'
    structuredPrd.value = null
    missingFields.value = []
    crossProjectWarning.value = null
    lastTaskId.value = null
    lastError.value = null
  }

  return {
    messages, candidates, clarificationStatus, structuredPrd,
    missingFields, connecting, crossProjectWarning, lastTaskId, lastPeakPrompt, pendingGoalText, lastError,
    connectChatWs, send, handleChatResponse, confirmPrd, confirm, dismissWarning, resubmitWithDefer, resubmitWithUrgent,
    disconnect, restoreMessages, reset,
  }
})
