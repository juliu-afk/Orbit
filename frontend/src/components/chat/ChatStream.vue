<script setup lang="ts">
/** 聊天流式输出组件——通过 SSE 接收 Agent 流式输出.

 * 流式连接逻辑见 composables/useAgentStream.ts。
 */
import { computed, onMounted, onUnmounted } from 'vue'
import { useAgentStream } from '@/composables/useAgentStream'

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

const apiBase = computed(() => props.baseUrl || window.location.origin)

const { messages, isStreaming, isThinking, currentText, start, cancel } =
  useAgentStream(props.agentId, props.taskId, apiBase.value)

onMounted(() => { start() })
onUnmounted(() => { cancel() })
</script>

<template>
  <div class="chat-stream">
    <div class="stream-header">
      <span class="agent-label">Agent: {{ agentId }}</span>
      <span v-if="isStreaming" class="status-badge running">流式中</span>
      <span v-else class="status-badge idle">空闲</span>
      <button v-if="isStreaming" class="cancel-btn" @click="cancel">取消</button>
    </div>

    <div class="message-list">
      <div v-for="msg in messages" :key="msg.id" :class="['message', msg.role]">
        <span class="msg-type">{{ msg.type }}</span>
        <pre class="msg-content">{{ msg.content }}</pre>
      </div>

      <div v-if="currentText" class="message assistant streaming">
        <pre class="msg-content">{{ currentText }}<span class="cursor">▌</span></pre>
      </div>

      <div v-if="isThinking && !currentText" class="message thinking">
        <span class="thinking-dots">Agent 思考中<span class="dots">...</span></span>
      </div>
    </div>
  </div>
</template>

<style scoped>
.chat-stream { display: flex; flex-direction: column; height: 100%; }
.stream-header { display: flex; align-items: center; gap: 8px; padding: 8px 12px; background: #111; border-bottom: 1px solid #333; font-size: 13px; }
.agent-label { font-weight: 600; color: #aaa; }
.status-badge { padding: 2px 8px; border-radius: 12px; font-size: 11px; }
.status-badge.running { background: #1a3a2a; color: #4caf50; }
.status-badge.idle { background: #1a1a2a; color: #888; }
.cancel-btn { margin-left: auto; padding: 2px 8px; border: 1px solid #c44; background: transparent; color: #c44; border-radius: 4px; cursor: pointer; font-size: 12px; }
.message-list { flex: 1; overflow-y: auto; padding: 12px; }
.message { margin-bottom: 8px; padding: 8px 12px; border-radius: 6px; font-size: 13px; }
.message.assistant { background: #1a2a3a; color: #b0c4de; }
.message.tool { background: #1a1a2a; color: #888; font-size: 12px; }
.message.streaming { border-left: 2px solid #4caf50; }
.msg-type { font-size: 10px; color: #666; text-transform: uppercase; margin-bottom: 2px; display: block; }
.msg-content { margin: 0; white-space: pre-wrap; word-break: break-word; font-family: 'Consolas', 'Monaco', 'Courier New', monospace; }
.cursor { animation: blink 1s step-end infinite; color: #4caf50; }
@keyframes blink { 50% { opacity: 0; } }
.thinking-dots { color: #888; font-size: 13px; }
.dots { animation: dotPulse 1.5s infinite; }
@keyframes dotPulse { 0%,20% { opacity: 0; } 50% { opacity: 1; } 80%,100% { opacity: 0; } }
</style>
