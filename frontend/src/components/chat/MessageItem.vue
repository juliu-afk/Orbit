<script setup lang="ts">
// WHY 新建：替代 ChatPanel 的气泡渲染——终端风格：等宽字体 + 前缀 + ANSI 着色。
// 每条消息一个独立 DOM 节点，支持右键定位。
import type { ChatMessage } from '@/stores/chat'

const props = defineProps<{
  message: ChatMessage
}>()

const emit = defineEmits<{
  (e: 'contextmenu', event: MouseEvent): void
}>()

// 按消息来源决定前缀和颜色
function getPrefix(): string {
  switch (props.message.from) {
    case 'user': return 'You>'
    case 'agent': return props.message.role ? `agent [${props.message.role}]>` : 'agent>'
    case 'system': return '✦'
  }
}

function getPrefixColor(): string {
  switch (props.message.from) {
    case 'user': return 'var(--color-orbit-info)'
    case 'agent': return 'var(--color-orbit-accent)'
    case 'system': return 'var(--color-orbit-text-muted)'
  }
}

function getTextColor(): string {
  switch (props.message.from) {
    case 'user': return 'var(--color-orbit-info)'
    case 'system': return 'var(--color-orbit-text-secondary)'
    default: return 'var(--color-orbit-text)'
  }
}

function formatTime(ts: number): string {
  const d = new Date(ts)
  return d.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit', second: '2-digit' })
}
</script>

<template>
  <div
    class="message-item flex gap-2 py-0.5 px-4 selectable hover:bg-[var(--color-orbit-surface-hover)] transition-colors"
    :data-message-id="message.id"
    @contextmenu="emit('contextmenu', $event)"
  >
    <!-- 前缀 -->
    <span
      class="prefix shrink-0 select-none"
      :style="{ color: getPrefixColor() }"
    >
      {{ getPrefix() }}
    </span>

    <!-- 消息正文 -->
    <span
      class="content flex-1 whitespace-pre-wrap break-words"
      :style="{ color: getTextColor() }"
    >
      {{ message.text }}
    </span>

    <!-- 时间戳 -->
    <span
      class="timestamp shrink-0 select-none text-[10px] self-start"
      style="color: var(--color-orbit-text-muted);"
    >
      {{ formatTime(message.timestamp) }}
    </span>
  </div>
</template>

<style scoped>
.message-item {
  font-family: var(--font-mono);
  font-size: 13px;
  line-height: 1.6;
}
.prefix {
  min-width: fit-content;
}
.content {
  /* WHY 保留换行和空格：代码输出、工具调用结果需要原样展示 */
  white-space: pre-wrap;
}
</style>
