/** Chat Store??NL ??????????? Agent ?????
 *
 * ??????/????/??? PRD/???????
 * ????????? /api/v1/chat?ClarifierAgent????? LLM ???
 */
import { defineStore } from 'pinia'
import { ref } from 'vue'

export interface ChatMessage {
  id: string
  text: string
  from: 'user' | 'agent' | 'system'
  timestamp: number
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
  type: 'clarify' | 'task_created'
  reply: string
  clarification_status: 'clarifying' | 'ready'
  structured_prd: StructuredPRD | null
  missing_fields: string[]
  candidates?: Candidate[]
  // task_created ?
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
  const lastError = ref<string | null>(null)

  // chat WS ?????? /api/v1/chat???? /ws/dashboard?
  let chatWs: WebSocket | null = null

  /** ?? chat WebSocket??? /api/v1/chat ??? */
  function connectChatWs(sessionId: string, projectName: string) {
    // ?????????????/????????? WS URL ??
    void sessionId
    void projectName
    // ?????
    disconnect()

    const protocol = location.protocol === 'https:' ? 'wss:' : 'ws:'
    const url = `${protocol}//${location.host}/api/v1/chat`
    connecting.value = true
    chatWs = new WebSocket(url)

    chatWs.onopen = () => {
      connecting.value = false
    }

    chatWs.onmessage = (event: MessageEvent) => {
      try {
        const resp = JSON.parse(event.data as string)
        handleChatResponse(resp)
      } catch {
        console.warn('[chat] ??????', event.data)
      }
    }

    chatWs.onclose = () => {
      connecting.value = false
      chatWs = null
    }

    chatWs.onerror = () => {
      connecting.value = false
      lastError.value = '????'
    }
  }

  /** ????? chat ???{code, data, message} ??? */
  function handleChatResponse(resp: { code: number; data: ClarifyResponse; message: string }) {
    if (resp.code !== 0) {
      lastError.value = resp.message
      // ???????????
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

    if (data.type === 'task_created') {
      // ?????????
      lastTaskId.value = data.task_id ?? null
      messages.value.push({
        id: `t-${Date.now()}`,
        text: data.reply ?? `??????${data.task_id}???????`,
        from: 'system',
        timestamp: Date.now(),
      })
      return
    }

    // clarify ??
    clarificationStatus.value = data.clarification_status
    structuredPrd.value = data.structured_prd
    missingFields.value = data.missing_fields || []
    if (data.candidates) {
      candidates.value = data.candidates
    }

    // Agent ????????
    messages.value.push({
      id: `a-${Date.now()}`,
      text: data.reply,
      from: 'agent',
      timestamp: Date.now(),
    })
    if (messages.value.length > 50) {
      messages.value = messages.value.slice(-50)
    }
  }

  /** ?????? */
  function send(text: string, sessionId: string, projectName: string) {
    if (!text.trim()) return
    if (!chatWs || chatWs.readyState !== WebSocket.OPEN) {
      lastError.value = '?????????'
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

  /** ?? PRD???????? */
  function confirmPrd(sessionId: string, projectName: string, modifiedPrd?: StructuredPRD) {
    if (!chatWs || chatWs.readyState !== WebSocket.OPEN) {
      lastError.value = '?????'
      return
    }

    const payload: Record<string, unknown> = {
      type: 'confirm',
      session_id: sessionId,
      project_name: projectName,
    }
    // ????? modified_prd????????????? prd ???
    if (modifiedPrd) {
      payload.modified_prd = modifiedPrd
    } else if (structuredPrd.value) {
      payload.modified_prd = structuredPrd.value
    }

    chatWs.send(JSON.stringify(payload))
  }

  /** ????????????????? */
  function confirm(_projectName?: string) {
    candidates.value = []
  }

  /** ??????? */
  function dismissWarning() {
    crossProjectWarning.value = null
  }

  /** ?? chat WS */
  function disconnect() {
    if (chatWs) {
      chatWs.close()
      chatWs = null
    }
    connecting.value = false
  }

  /** ???????? sessionStore ??? */
  function restoreMessages(msgs: Array<{ role: string; content: string; created_at: number }>) {
    messages.value = msgs.map((m, i) => ({
      id: `r-${i}`,
      text: m.content,
      from: m.role === 'user' ? 'user' : 'agent',
      timestamp: m.created_at * 1000,
    }))
  }

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
    missingFields, connecting, crossProjectWarning, lastTaskId, lastError,
    connectChatWs, send, handleChatResponse, confirmPrd, confirm, dismissWarning,
    disconnect, restoreMessages, reset,
  }
})
