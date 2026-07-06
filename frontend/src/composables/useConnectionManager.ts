/** UX-5: 统一连接管理——聚合 WS + SSE + HTTP 连接状态。

 * WHY: 三套独立连接各自管理状态，无统一视图。
 * 本 composable 聚合连接状态，提供单一 overall 状态。
 */
import { computed, type Ref } from 'vue'

export type ConnStatus = 'connected' | 'connecting' | 'disconnected'

export interface ConnectionState {
  ws: Ref<ConnStatus>
  sse: Ref<ConnStatus>
  http: Ref<ConnStatus>
}

export function useConnectionManager(state: ConnectionState) {
  const overall = computed<ConnStatus>(() => {
    if (state.ws.value === 'disconnected' && state.sse.value === 'disconnected') return 'disconnected'
    if (state.ws.value === 'connecting' || state.sse.value === 'connecting') return 'connecting'
    return 'connected'
  })

  const isDegraded = computed(() =>
    overall.value === 'connected' &&
    (state.ws.value !== 'connected' || state.sse.value !== 'connected')
  )

  return { overall, isDegraded }
}
