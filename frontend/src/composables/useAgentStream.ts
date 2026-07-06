/** Agent SSE 流式连接——从 ChatStream.vue 拆分。 */

import { ref, computed } from 'vue'
import { useEventSource } from '@/composables/useEventSource'
import type { StreamEvent } from '@/types/stream'

interface DisplayMessage {
  id: string
  role: 'assistant' | 'user' | 'tool'
  content: string
  timestamp: number
  type?: string
}

export function useAgentStream(agentId: string, taskId: string, baseUrl: string) {
  const messages = ref<DisplayMessage[]>([])
  const isStreaming = ref(false)
  const isThinking = ref(false)
  const currentText = ref('')
  const sse = useEventSource()
  const msgCounter = ref(0)
  const _onFinish: Array<(result: Record<string, unknown>) => void> = []
  const _onError: Array<(message: string) => void> = []

  const apiBase = computed(() => baseUrl || window.location.origin)

  function nextId(): string {
    return `msg-${++msgCounter.value}`
  }

  function onFinish(fn: (result: Record<string, unknown>) => void) {
    _onFinish.push(fn)
  }

  function onError(fn: (message: string) => void) {
    _onError.push(fn)
  }

  async function start() {
    isStreaming.value = true
    isThinking.value = true
    messages.value = []

    let tid = taskId
    if (!tid) {
      try {
        const resp = await fetch(`${apiBase.value}/api/v1/agent/${agentId}/run`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ task: '', context: {} }),
        })
        const body = await resp.json()
        tid = body.data?.task_id
        if (!tid) {
          _onError.forEach(fn => fn('无法启动 Agent 任务'))
          isStreaming.value = false
          return
        }
      } catch (e) {
        _onError.forEach(fn => fn(`启动失败: ${String(e)}`))
        isStreaming.value = false
        return
      }
    }
    sse.setTaskId(tid)

    sse.setEventHandler((event: StreamEvent) => {
      switch (event.type) {
        case 'text_delta': {
          currentText.value += String(event.data.delta ?? '')
          break
        }
        case 'thinking': {
          isThinking.value = true
          break
        }
        case 'tool_call': {
          isThinking.value = false
          const toolCalls = event.data.tool_calls as Array<{ function: { name: string; arguments: string } }> | undefined
          if (toolCalls) {
            for (const tc of toolCalls) {
              const name = tc.function?.name ?? 'unknown'
              const args = tc.function?.arguments ?? '{}'
              messages.value.push({
                id: nextId(), role: 'tool',
                content: `${name}(${args.length > 80 ? args.slice(0, 80) + '...' : args})`,
                timestamp: Date.now(), type: 'tool_call',
              })
            }
          }
          break
        }
        case 'tool_result': {
          const tool = String(event.data.tool ?? '')
          const truncated = Boolean(event.data.truncated)
          messages.value.push({
            id: nextId(), role: 'tool',
            content: truncated ? `${tool}: 结果已截断` : `${tool}: 完成`,
            timestamp: Date.now(), type: 'tool_result',
          })
          break
        }
        case 'finish_step': {
          isStreaming.value = false
          isThinking.value = false
          const output = String(event.data.output ?? currentText.value)
          if (output && !messages.value.some(m => m.content === output)) {
            messages.value.push({
              id: nextId(), role: 'assistant', content: output,
              timestamp: Date.now(), type: 'finish',
            })
          }
          _onFinish.forEach(fn => fn(event.data))
          break
        }
        case 'error': {
          const msg = String(event.data.message ?? '未知错误')
          messages.value.push({
            id: nextId(), role: 'assistant', content: `错误: ${msg}`,
            timestamp: Date.now(), type: 'error',
          })
          _onError.forEach(fn => fn(msg))
          break
        }
        case 'cancelled': {
          isStreaming.value = false
          isThinking.value = false
          messages.value.push({
            id: nextId(), role: 'assistant', content: '已取消',
            timestamp: Date.now(), type: 'cancelled',
          })
          break
        }
      }
    })

    sse.connect(`${apiBase.value}/api/v1/agent/${agentId}/stream?task_id=${tid}`)
  }

  async function cancel() {
    const tid = sse.taskId.value
    if (tid) {
      try {
        await fetch(`${apiBase.value}/api/v1/agent/${agentId}/cancel`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ task_id: tid }),
        })
      } catch {
        // 取消失败不阻塞
      }
    }
    sse.disconnect()
  }

  return { messages, isStreaming, isThinking, currentText, start, cancel, onFinish, onError }
}
