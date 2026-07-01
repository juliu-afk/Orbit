<script setup lang="ts">
import type { ChatMessage } from '@/stores/chat'
const props = defineProps<{ message: ChatMessage }>()
const emit = defineEmits<{ (e: 'dismiss'): void }>()
function trunc(s: string, m = 80) { return s.length <= m ? s : s.slice(0, m) + '...' }
function author() { switch (props.message.from) { case 'user': return 'You'; case 'agent': return props.message.role || 'agent'; default: return 'system' } }
</script>
<template>
<div class="flex items-center gap-2 px-3 py-1.5 mx-3 mb-1 rounded text-xs select-none" style="background:var(--color-orbit-surface);border-left:3px solid var(--color-orbit-accent);font-family:var(--font-mono)">
  <span style="color:var(--color-orbit-accent)">{{ author() }}></span>
  <span class="flex-1 truncate" style="color:var(--color-orbit-text-secondary)">{{ trunc(message.text) }}</span>
  <button style="color:var(--color-orbit-text-muted);background:none;border:none;cursor:pointer" @click="emit('dismiss')">x</button>
</div>
</template>
