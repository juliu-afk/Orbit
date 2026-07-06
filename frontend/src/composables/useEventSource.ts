/** SSE 连接管理 composable.

 * P1-1: fetch 替代 EventSource——原生 EventSource 不支持自定义 HTTP Header，
 * token 只能经 URL 查询参数传递，泄露到日志/浏览器历史/Referer。
 * fetch + ReadableStream 支持 X-Orbit-Token header，消除 URL 泄露。

 * 与 useWebSocket.ts 互补——WebSocket 用于 Dashboard 实时更新,
 * SSE 用于 Agent 执行流式输出。

 * P2-2: 增加重连上限——有限重连而非无限。
 */
import { ref, type Ref } from 'vue'
import type { StreamEvent, StreamEventType } from '@/types/stream'

export type ConnectionStatus = 'connecting' | 'connected' | 'disconnected'

const MAX_RECONNECT = 5

export function useEventSource() {
  const eventSource: Ref<EventSource | null> = ref(null)
  const connectionStatus: Ref<ConnectionStatus> = ref('disconnected')
  const taskId: Ref<string | null> = ref(null)
  const retryCount = ref(0)

  let onEvent: ((event: StreamEvent) => void) | null = null
  let abortController: AbortController | null = null

  function setEventHandler(handler: (event: StreamEvent) => void) {
    onEvent = handler
  }

  /** P1-1: fetch-based SSE——支持 X-Orbit-Token header，防止 token 泄露到 URL。 */
  async function connect(url: string) {
    disconnect()
    connectionStatus.value = 'connecting'
    retryCount.value = 0

    const token = localStorage.getItem('orbitAuthToken') || ''
    abortController = new AbortController()

    try {
      const response = await fetch(url, {
        headers: token ? { 'X-Orbit-Token': token } : {},
        signal: abortController.signal,
      })

      if (!response.ok) {
        connectionStatus.value = 'disconnected'
        retryCount.value++
        if (retryCount.value < MAX_RECONNECT) {
          const delay = Math.min(1000 * Math.pow(2, retryCount.value - 1), 16000)
          setTimeout(() => connect(url), delay)
        }
        return
      }

      connectionStatus.value = 'connected'
      retryCount.value = 0

      const reader = response.body!.getReader()
      const decoder = new TextDecoder()
      let buffer = ''

      while (true) {
        const { done, value } = await reader.read()
        if (done) break

        buffer += decoder.decode(value, { stream: true })
        const lines = buffer.split('\n')
        buffer = lines.pop() || ''  // 未完成的行留到下次

        let currentEventType = ''
        for (const line of lines) {
          if (line.startsWith('event: ')) {
            currentEventType = line.slice(7).trim()
          } else if (line.startsWith('data: ')) {
            const raw = line.slice(6)
            try {
              const parsed = JSON.parse(raw)
              onEvent?.({
                type: currentEventType as StreamEventType,
                taskId: parsed.task_id ?? '',
                agentId: parsed.agent_id ?? '',
                turn: parsed.turn ?? 0,
                data: parsed.data ?? {},
              })
            } catch {
              if (import.meta.env.DEV)
                console.warn('[useEventSource] 事件解析失败', currentEventType, raw.slice(0, 100))
            }
          }
        }
      }
    } catch (err: unknown) {
      if (err instanceof DOMException && err.name === 'AbortError') return
      connectionStatus.value = 'disconnected'
    }
  }

  function disconnect() {
    retryCount.value = MAX_RECONNECT
    abortController?.abort()
    abortController = null
    eventSource.value = null
    connectionStatus.value = 'disconnected'
    taskId.value = null
  }

  function setTaskId(id: string) {
    taskId.value = id
  }

  return {
    eventSource,
    connectionStatus,
    taskId,
    retryCount,
    connect,
    disconnect,
    setTaskId,
    setEventHandler,
  }
}
