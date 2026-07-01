<script setup lang="ts">
// WHY 新建：微信风格的引用气泡——右键消息→"引用"→此 chip 出现在输入框上方。
// 发送消息或点 ✕ 时消失。
import type { ChatMessage } from '@/stores/chat'

const props = defineProps<{
  message: ChatMessage
}>()

const emit = defineEmits<{
  (e: 'dismiss'): void
}>()

function truncate(text: string, maxLen = 80): string {
  if (text.length <= maxLen) return text
  return text.slice(0, maxLen) + '...'
}

function authorLabel(): string {
  switch (props.message.from) {
    case 'user': return 'You'
    case 'agent': return props.message.role || 'agent'
    case 'system': return 'system'
  }
}
</script>

<template>
  <div
    class="quote-chip flex items-center gap-2 px-3 py-1.5 mx-3 mb-1 rounded text-xs select-none"
    style="
      background: var(--color-orbit-surface);
      border-left: 3px solid var(--color-orbit-accent);
      font-family: var(--font-mono);
    "
  >
    <span style="color: var(--color-orbit-accent);">
      {{ authorLabel() }}>
    </span>
    <span class="flex-1 truncate" style="color: var(--color-orbit-text-secondary);">
      {{ truncate(message.text) }}
    </span>
    <button
      class="dismiss-btn text-xs cursor-pointer"
      style="color: var(--color-orbit-text-muted); background: none; border: none;"
      @click="emit('dismiss')"
      title="取消引用"
    >
      ✕
    </button>
  </div>
</template>

<style scoped>
.dismiss-btn:hover {
  color: var(--color-orbit-error);
}
</style>
