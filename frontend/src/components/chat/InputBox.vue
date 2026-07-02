<script setup lang="ts">
import { ref, computed } from 'vue'
const emit = defineEmits<{ (e: 'send', text: string): void; (e: 'navigate-history', d: -1 | 1): void }>()
const inputRef = ref<HTMLTextAreaElement | null>(null)
const inputText = ref('')
// P1-1 fix: 后端 /api/v1/commands 端点不存在，退回硬编码。
// 后续 v0.23 实现后端端点时改为 apiGet fallback 模式。
const CMDS = ['/task', '/review', '/dream', '/search', '/help', '/compose']
const showAC = ref(false)
const acIdx = ref(0)
const filtered = computed(() => {
  if (!inputText.value.startsWith('/') || inputText.value.includes(' ')) return []
  return CMDS.filter(c => c.startsWith(inputText.value))
})
function onKey(e: KeyboardEvent) {
  if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); const t = inputText.value.trim(); if (t) { emit('send', t); inputText.value = ''; showAC.value = false } }
  if (e.key === 'Tab') { e.preventDefault(); if (filtered.value.length > 0) { if (!showAC.value) { showAC.value = true } else { acIdx.value = (acIdx.value + 1) % filtered.value.length } } }
  if (e.key === 'ArrowUp' && inputText.value === '') { e.preventDefault(); emit('navigate-history', -1) }
  if (e.key === 'ArrowDown' && inputText.value === '') { e.preventDefault(); emit('navigate-history', 1) }
  if (e.key === 'Escape') { showAC.value = false }
}
function focus() { inputRef.value?.focus() }
defineExpose({ focus })
</script>
<template>
<div class="input-box">
  <div class="flex items-start gap-2 px-3 py-2">
    <span class="shrink-0 select-none" style="color:var(--color-orbit-accent);font-family:var(--font-mono);font-size:14px">$</span>
    <textarea ref="inputRef" v-model="inputText" class="flex-1 resize-none outline-none" style="background:transparent;border:none;color:var(--color-orbit-text);font-family:var(--font-mono);font-size:13px;line-height:1.6;caret-color:var(--color-orbit-accent)" rows="1" placeholder="/help..." @keydown="onKey" />
  </div>
</div>
</template>
