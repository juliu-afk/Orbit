/** 原生 WebSocket 连接管理 composable。
 *
 * WHY 原生而非 Socket.IO：场景简单（订阅→推送），
 * 浏览器 WebSocket API 已足够成熟，零依赖，全可控。
 *
 * 指数退避重连：1s → 2s → 4s → 8s → 16s，最多 5 次。
 */
import { ref } from 'vue'
import type { WsMessage } from '@/types/dashboard'

export type ConnectionStatus = 'connecting' | 'connected' | 'disconnected'

export function useWebSocket() {
  const ws = ref<WebSocket | null>(null)
  const connectionStatus = ref<ConnectionStatus>('disconnected')
  const retryCount = ref(0)
  const maxRetries = 5
  const currentTaskId = ref<string | null>(null)
  let reconnectTimer: ReturnType<typeof setTimeout> | null = null

  /** 消息路由回调。外部设置此函数将 WS 消息分发到各 Store。 */
  let onMessage: ((msg: WsMessage) => void) | null = null

  function setMessageHandler(handler: (msg: WsMessage) => void) {
    onMessage = handler
  }

  function connect(url: string) {
    // 清理旧连接
    if (ws.value) {
      ws.value.close()
      ws.value = null
    }

    connectionStatus.value = 'connecting'
    ws.value = new WebSocket(url)

    ws.value.onopen = () => {
      connectionStatus.value = 'connected'
      retryCount.value = 0
      // 重连后自动恢复订阅
      if (currentTaskId.value) {
        sendSubscribe(currentTaskId.value)
      }
    }

    ws.value.onmessage = (event: MessageEvent) => {
      try {
        const msg: WsMessage = JSON.parse(event.data as string)
        onMessage?.(msg)
      } catch {
        console.warn('[useWebSocket] 消息解析失败', event.data)
      }
    }

    ws.value.onerror = () => {
      // onclose 在 error 后触发，统一在 onclose 处理重连
    }

    ws.value.onclose = (event: CloseEvent) => {
      connectionStatus.value = 'disconnected'
      ws.value = null
      // 非正常关闭 + 未达重试上限 → 指数退避重连
      if (!event.wasClean && retryCount.value < maxRetries) {
        scheduleReconnect(url)
      }
    }
  }

  function scheduleReconnect(url: string) {
    // 指数退避：1s/2s/4s/8s/16s
    const delay = Math.min(1000 * Math.pow(2, retryCount.value), 16000)
    retryCount.value++
    reconnectTimer = setTimeout(() => connect(url), delay)
  }

  function subscribe(taskId: string) {
    currentTaskId.value = taskId
    sendSubscribe(taskId)
  }

  function sendSubscribe(taskId: string) {
    if (ws.value && connectionStatus.value === 'connected') {
      ws.value.send(JSON.stringify({ type: 'subscribe', task_id: taskId }))
    }
  }

  function disconnect() {
    if (reconnectTimer) {
      clearTimeout(reconnectTimer)
      reconnectTimer = null
    }
    retryCount.value = maxRetries // 阻止自动重连
    ws.value?.close(1000, 'client disconnect')
    ws.value = null
    connectionStatus.value = 'disconnected'
  }

  return {
    connectionStatus,
    retryCount,
    maxRetries,
    connect,
    disconnect,
    subscribe,
    setMessageHandler,
  }
}
