<script setup lang="ts">
import type { ChatMessage } from '@/stores/chat'
const props = defineProps<{ message: ChatMessage }>()
const emit = defineEmits<{ (e: 'contextmenu', event: MouseEvent): void }>()
function prefix(): string {
  switch (props.message.from) {
    case 'user': return 'You>'
    case 'agent': return props.message.role ? `agent[${props.message.role}]>` : 'agent>'
    case 'system': return ''
  }
}
function prefixColor(): string {
  switch (props.message.from) {
    case 'user': return 'var(--color-orbit-info)'
    case 'agent': return 'var(--color-orbit-accent)'
    default: return 'var(--color-orbit-text-muted)'
  }
}
function fmt(ts: number) {
  return new Date(ts).toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit', second: '2-digit' })
}
</script>
<template>
<div class="message-item flex gap-2 py-0.5 px-4 selectable" :data-message-id="message.id" @contextmenu="emit('contextmenu', $event)" style="font-family:var(--font-mono);font-size:13px;line-height:1.6">
  <span class="shrink-0 select-none" :style="{ color: prefixColor() }">{{ prefix() }}</span>
  <span class="flex-1 whitespace-pre-wrap break-words" :style="{ color: props.message.from === 'user' ? 'var(--color-orbit-info)' : props.message.from === 'system' ? 'var(--color-orbit-text-secondary)' : 'var(--color-orbit-text)' }">{{ message.text }}</span>
  <span class="shrink-0 select-none text-[10px] self-start" style="color:var(--color-orbit-text-muted)">{{ fmt(message.timestamp) }}</span>
</div>
</template>
