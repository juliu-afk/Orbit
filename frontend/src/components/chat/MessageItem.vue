<script setup lang="ts">
import { computed } from 'vue'
import type { ChatMessage } from '@/stores/chat'

const props = defineProps<{ message: ChatMessage }>()
const emit = defineEmits<{ (e: 'contextmenu', event: MouseEvent): void; (e: 'open-code', code: string): void }>()

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

// WHY 代码块解析: 聊天消息中 ``` 包裹的代码应渲染为等宽高亮块，非纯文本
interface Segment {
  type: 'text' | 'code'
  content: string
}
const segments = computed<Segment[]>(() => {
  const parts = props.message.text.split(/(```[a-z]*\n?)/)
  const result: Segment[] = []
  let inCode = false
  for (const part of parts) {
    if (part.startsWith('```')) {
      inCode = !inCode
      continue
    }
    if (part) {
      result.push({ type: inCode ? 'code' : 'text', content: part })
    }
  }
  return result
})

</script>

<template>
<div class="message-item flex gap-2 py-0.5 px-4 selectable" :data-message-id="message.id" @contextmenu="emit('contextmenu', $event)" style="font-family:var(--font-mono);font-size:13px;line-height:1.6">
  <span class="shrink-0 select-none" :style="{ color: prefixColor() }">{{ prefix() }}</span>
  <div class="flex-1" :style="{ color: props.message.from === 'user' ? 'var(--color-orbit-info)' : props.message.from === 'system' ? 'var(--color-orbit-text-secondary)' : 'var(--color-orbit-text)' }">
    <template v-for="(seg, _i) in segments" :key="_i">
      <span v-if="seg.type === 'text'" class="whitespace-pre-wrap break-words">{{ seg.content }}</span>
      <pre v-else class="code-block"><code>{{ seg.content }}</code><button class="code-open-btn" @click="emit('open-code', seg.content)" title="Open in Monaco">&#x2197;</button></pre>
    </template>
  </div>
  <span class="shrink-0 select-none text-[10px] self-start" style="color:var(--color-orbit-text-muted)">{{ fmt(message.timestamp) }}</span>
</div>
</template>

<style scoped>
.code-block {
  margin: 4px 0; padding: 8px 10px; border-radius: 4px;
  background: rgba(15, 15, 26, 0.9); border: 1px solid var(--color-orbit-border);
  font-family: 'Cascadia Code', 'Fira Code', 'Consolas', monospace;
  font-size: 12px; line-height: 1.5;
  color: var(--color-orbit-text); overflow-x: auto;
  position: relative; white-space: pre-wrap; word-break: break-word;
}
.code-open-btn {
  position: absolute; top: 4px; right: 4px;
  background: rgba(255,255,255,0.06); border: 1px solid var(--color-orbit-border);
  color: var(--color-orbit-text-muted); cursor: pointer;
  font-size: 12px; padding: 2px 6px; border-radius: 3px;
  font-family: var(--font-mono); opacity: 0; transition: opacity 0.15s;
}
.code-block:hover .code-open-btn { opacity: 1; }
.code-open-btn:hover { background: var(--color-orbit-accent); color: #fff; border-color: var(--color-orbit-accent); }
</style>
