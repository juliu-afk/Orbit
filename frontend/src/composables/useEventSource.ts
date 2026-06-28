/** SSE 连接管理 composable.

 * WHY EventSource 而非 WebSocket: SSE 是浏览器原生单向流，
 * 适合 Agent 流式输出（只读）。取消操作走独立 POST 端点。

 * 与 useWebSocket.ts 互补——WebSocket 用于 Dashboard 实时更新,
 * SSE 用于 Agent 执行流式输出。
 */
import { ref, type Ref } from 'vue'
import type { StreamEvent, StreamEventType } from '@/types/stream'

export type ConnectionStatus = 'connecting' | 'connected' | 'disconnected'

const EVENT_TYPES: StreamEventType[] = [
  'text_delta', 'thinking', 'tool_call', 'tool_result',
  'turn_start', 'finish_step', 'error', 'cancelled',
]

export function useEventSource() {
  const eventSource: Ref<EventSource | null> = ref(null)
  const connectionStatus: Ref<ConnectionStatus> = ref('disconnected')
  const taskId: Ref<string | null> = ref(null)

  let onEvent: ((event: StreamEvent) => void) | null = null

  function setEventHandler(handler: (event: StreamEvent) => void) {
    onEvent = handler
  }

  function connect(url: string) {
    disconnect()
    connectionStatus.value = 'connecting'

    const es = new EventSource(url)
    eventSource.value = es

    es.onopen = () => {
      connectionStatus.value = 'connected'
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
          console.warn('[useEventSource] 事件解析失败', eventType, e.data)
        }
      })
    }

    es.onerror = () => {
      connectionStatus.value = 'disconnected'
      // EventSource 自动重连——无需手动处理
    }
  }

  function disconnect() {
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
    connect,
    disconnect,
    setTaskId,
    setEventHandler,
  }
}
