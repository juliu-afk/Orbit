/** SSE 连接管理 composable.

 * WHY EventSource 而非 WebSocket: SSE 是浏览器原生单向流，
 * 适合 Agent 流式输出（只读）。取消操作走独立 POST 端点。

 * 与 useWebSocket.ts 互补——WebSocket 用于 Dashboard 实时更新,
 * SSE 用于 Agent 执行流式输出。

 * P2-2: 增加重连上限——EventSource 默认无限重连，
 * 服务端持续非 200 时消耗客户端资源。限制最多 5 次重连。
 */
import { ref, type Ref } from 'vue'
import type { StreamEvent, StreamEventType } from '@/types/stream'

export type ConnectionStatus = 'connecting' | 'connected' | 'disconnected'

const EVENT_TYPES: StreamEventType[] = [
  'text_delta', 'thinking', 'tool_call', 'tool_result',
  'turn_start', 'finish_step', 'error', 'cancelled',
]

const MAX_RECONNECT = 5

export function useEventSource() {
  const eventSource: Ref<EventSource | null> = ref(null)
  const connectionStatus: Ref<ConnectionStatus> = ref('disconnected')
  const taskId: Ref<string | null> = ref(null)
  const retryCount = ref(0)

  let onEvent: ((event: StreamEvent) => void) | null = null

  function setEventHandler(handler: (event: StreamEvent) => void) {
    onEvent = handler
  }

  function connect(url: string) {
    disconnect()
    connectionStatus.value = 'connecting'
    retryCount.value = 0

    const es = new EventSource(url)
    eventSource.value = es

    es.onopen = () => {
      connectionStatus.value = 'connected'
      retryCount.value = 0
    }

    for (const eventType of EVENT_TYPES) {
      es.addEventListener(eventType, (e: MessageEvent) => {
        try {
          const raw = JSON.parse(e.data as string)
          onEvent?.({
            type: eventType,
            taskId: raw.task_id ?? '',
            agentId: raw.agent_id ?? '',
            turn: raw.turn ?? 0,
            data: raw.data ?? {},
          })
        } catch {
          if (import.meta.env.DEV) console.warn('[useEventSource] 事件解析失败', eventType, e.data)
        }
      })
    }

    es.onerror = () => {
      connectionStatus.value = 'disconnected'
      // P2-2: 有限重连——超限后彻底断开
      retryCount.value++
      if (retryCount.value >= MAX_RECONNECT) {
        if (import.meta.env.DEV) console.warn('[useEventSource] 已达重连上限', MAX_RECONNECT)
        es.close()
        eventSource.value = null
      }
    }
  }

  function disconnect() {
    retryCount.value = MAX_RECONNECT // 阻止自动重连
    eventSource.value?.close()
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
