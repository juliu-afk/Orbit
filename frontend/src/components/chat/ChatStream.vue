<script setup lang="ts">
/** 聊天流式输出组件——通过 SSE 接收 Agent 流式输出.

 * 展示: text_delta 流式文本、thinking 思考过程、
 *       tool_call/tool_result 工具调用、finish_step 完成标记。

 * 流程: POST /api/v1/agents/{agentId}/run → taskId
 *      → EventSource(/api/v1/agents/{agentId}/stream?taskId=...)
 */
import { ref, computed, onMounted, onUnmounted, watch } from 'vue'
import { useEventSource } from '@/composables/useEventSource'
import type { StreamEvent } from '@/types/stream'

const props = withDefaults(defineProps<{
  agentId: string
  taskId?: string
  baseUrl?: string
}>(), {
  taskId: '',
  baseUrl: '',
})

const emit = defineEmits<{
  (e: 'finish', result: Record<string, unknown>): void
  (e: 'error', message: string): void
}>()

interface DisplayMessage {
  id: string
  role: 'assistant' | 'user' | 'tool'
  content: string
  timestamp: number
  type?: string
}

const messages = ref<DisplayMessage[]>([])
const isStreaming = ref(false)
const isThinking = ref(false)
const currentText = ref('')
const sse = useEventSource()
const msgCounter = ref(0)

const apiBase = computed(() => props.baseUrl || window.location.origin)

function nextId(): string {
  return `msg-${++msgCounter.value}`
}

async function startStream() {
  isStreaming.value = true
  isThinking.value = true
  messages.value = []

  // 1. POST 启动 Agent 执行，获取 task_id
  let tid = props.taskId
  if (!tid) {
    try {
      const resp = await fetch(`${apiBase.value}/api/v1/agents/${props.agentId}/run`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ task: '', context: {} }),
      })
      const body = await resp.json()
      tid = body.data?.task_id
      if (!tid) {
        emit('error', '无法启动 Agent 任务')
        isStreaming.value = false
        return
      }
    } catch (e) {
      emit('error', `启动失败: ${String(e)}`)
      isStreaming.value = false
      return
    }
  }
  sse.setTaskId(tid)

  // 2. SSE 连接流式接收事件
  sse.setEventHandler((event: StreamEvent) => {
    switch (event.type) {
      case 'text_delta': {
        const delta = String(event.data.delta ?? '')
        currentText.value += delta
        // 滚动到最后
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
              id: nextId(),
              role: 'tool',
              content: `${name}(${args.length > 80 ? args.slice(0, 80) + '...' : args})`,
              timestamp: Date.now(),
              type: 'tool_call',
            })
          }
        }
        break
      }
      case 'tool_result': {
        const tool = String(event.data.tool ?? '')
        const truncated = Boolean(event.data.truncated)
        messages.value.push({
          id: nextId(),
          role: 'tool',
          content: truncated ? `${tool}: 结果已截断` : `${tool}: 完成`,
          timestamp: Date.now(),
          type: 'tool_result',
        })
        break
      }
      case 'finish_step': {
        isStreaming.value = false
        isThinking.value = false
        const output = String(event.data.output ?? currentText.value)
        if (output && !messages.value.some(m => m.content === output)) {
          messages.value.push({
            id: nextId(),
            role: 'assistant',
            content: output,
            timestamp: Date.now(),
            type: 'finish',
          })
        }
        emit('finish', event.data)
        break
      }
      case 'error': {
        const msg = String(event.data.message ?? '未知错误')
        messages.value.push({
          id: nextId(),
          role: 'assistant',
          content: `错误: ${msg}`,
          timestamp: Date.now(),
          type: 'error',
        })
        emit('error', msg)
        break
      }
      case 'cancelled': {
        isStreaming.value = false
        isThinking.value = false
        messages.value.push({
          id: nextId(),
          role: 'assistant',
          content: '已取消',
          timestamp: Date.now(),
          type: 'cancelled',
        })
        break
      }
    }
  })

  const streamUrl = `${apiBase.value}/api/v1/agents/${props.agentId}/stream?task_id=${tid}`
  sse.connect(streamUrl)
}

async function cancel() {
  const tid = sse.taskId.value
  if (tid) {
    try {
      await fetch(`${apiBase.value}/api/v1/agents/${props.agentId}/cancel`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ task_id: tid }),
      })
    } catch {
      // 取消失败不阻塞
    }
  }
  sse.disconnect()
  isStreaming.value = false
  isThinking.value = false
}

// 挂载时若 agentId + taskId 均已提供，自动启动流
// WHY: ChatPanel PRD 确认后传入 lastTaskId，无需用户手动触发
onMounted(() => {
  if (props.agentId && props.taskId) {
    startStream()
  }
})

// taskId 变更时自动切换流——先 cancel 旧流再启动新流
// WHY: 与 agentId watcher 一致——taskId 变化等同于任务变更
watch(() => props.taskId, (newId, oldId) => {
  if (oldId && oldId !== newId && isStreaming.value) {
    cancel()  // 中断旧流
  }
  if (newId && props.agentId) {
    currentText.value = ''
    messages.value = []
    startStream()
  }
})

// 当 agentId 变化时自动重启
watch(() => props.agentId, () => {
  if (isStreaming.value) {
    cancel()
  }
  currentText.value = ''
  messages.value = []
  if (props.taskId) {
    startStream()
  }
})

onUnmounted(() => {
  sse.disconnect()
})

defineExpose({ startStream, cancel, messages, isStreaming, currentText })
</script>

<template>
  <div class="chat-stream">
    <div class="stream-header">
      <span class="agent-label">Agent: {{ agentId }}</span>
      <span v-if="isStreaming" class="status-badge running">流式中</span>
      <span v-else class="status-badge idle">空闲</span>
      <button
        v-if="isStreaming"
        class="cancel-btn"
        @click="cancel"
      >
        取消
      </button>
    </div>

    <div class="message-list">
      <div
        v-for="msg in messages"
        :key="msg.id"
        :class="['message', msg.role]"
      >
        <span class="msg-type">{{ msg.type }}</span>
        <pre class="msg-content">{{ msg.content }}</pre>
      </div>

      <!-- 流式文本实时展示 -->
      <div v-if="currentText" class="message assistant streaming">
        <pre class="msg-content">{{ currentText }}<span class="cursor">▌</span></pre>
      </div>

      <!-- 思考指示器 -->
      <div v-if="isThinking && !currentText" class="message thinking">
        <span class="thinking-dots">Agent 思考中<span class="dots">...</span></span>
      </div>
    </div>
  </div>
</template>

<style scoped>
.chat-stream {
  display: flex;
  flex-direction: column;
  height: 100%;
  border: 1px solid var(--border-color, #e0e0e0);
  border-radius: 8px;
  overflow: hidden;
  background: var(--bg-color, #fff);
}
.stream-header {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  border-bottom: 1px solid var(--border-color, #e0e0e0);
  background: var(--header-bg, #fafafa);
}
.agent-label { font-weight: 600; font-size: 13px; }
.status-badge { font-size: 11px; padding: 2px 6px; border-radius: 10px; }
.status-badge.running { background: #e6f7ff; color: #1890ff; }
.status-badge.idle { background: #f5f5f5; color: #999; }
.cancel-btn {
  margin-left: auto;
  padding: 2px 10px;
  border: 1px solid #ff4d4f;
  border-radius: 4px;
  background: #fff;
  color: #ff4d4f;
  cursor: pointer;
  font-size: 12px;
}
.message-list {
  flex: 1;
  overflow-y: auto;
  padding: 8px;
}
.message {
  margin-bottom: 6px;
  padding: 6px 10px;
  border-radius: 6px;
  max-width: 90%;
}
.message.assistant { background: #f0f5ff; align-self: flex-start; }
.message.tool { background: #fffbe6; align-self: flex-start; font-size: 12px; }
.message.thinking { background: transparent; }
.msg-type {
  font-size: 10px;
  color: #999;
  text-transform: uppercase;
}
.msg-content {
  margin: 2px 0 0;
  white-space: pre-wrap;
  word-break: break-word;
  font-size: 13px;
  line-height: 1.5;
}
.streaming .cursor {
  animation: blink 1s step-end infinite;
}
@keyframes blink {
  50% { opacity: 0; }
}
.thinking-dots .dots {
  animation: dotPulse 1.5s infinite;
}
@keyframes dotPulse {
  0%, 30% { opacity: 0.2; }
  50% { opacity: 1; }
  70%, 100% { opacity: 0.2; }
}
</style>
