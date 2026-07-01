<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue'
import type { ChatMessage } from '@/stores/chat'
const props = defineProps<{ message: ChatMessage; x: number; y: number }>()
const emit = defineEmits<{ (e: 'close'): void; (e: 'copy'): void; (e: 'quote'): void; (e: 'open-file'): void; (e: 'retry'): void }>()
const menuRef = ref<HTMLDivElement | null>(null)
const ax = ref(props.x)
const ay = ref(props.y)
// WHY 具名函数——onUnmounted 需要相同引用才能正确移除
function onClickOutside() { emit('close') }
function onEsc(e: KeyboardEvent) { if (e.key === 'Escape') emit('close') }
onMounted(() => {
  document.addEventListener('click', onClickOutside)
  document.addEventListener('keydown', onEsc)
  if (menuRef.value) { const r = menuRef.value.getBoundingClientRect(); if (props.x + r.width > window.innerWidth) ax.value = props.x - r.width; if (props.y + r.height > window.innerHeight) ay.value = props.y - r.height }
})
// P1-1 fix: 移除全局事件监听器，防止泄漏
onUnmounted(() => {
  document.removeEventListener('click', onClickOutside)
  document.removeEventListener('keydown', onEsc)
})
function hasFile() { return /\.(?:py|ts|vue|js|tsx|css|html|md)\b/.test(props.message.text) }
</script>
<template>
<Teleport to="body"><div ref="menuRef" class="rounded py-1 shadow-lg" :style="{ left: ax + 'px', top: ay + 'px', background: 'var(--color-orbit-surface)', border: '1px solid var(--color-orbit-border)', fontFamily: 'var(--font-mono)', fontSize: '12px', minWidth: '180px', zIndex: 10000 }" @click.stop>
  <div class="px-3 py-1.5 cursor-pointer flex items-center gap-2" style="color:var(--color-orbit-text)" @click="emit('copy')"> Copy</div>
  <div class="px-3 py-1.5 cursor-pointer flex items-center gap-2" style="color:var(--color-orbit-text)" @click="emit('quote')"> Quote</div>
  <div v-if="hasFile()" class="px-3 py-1.5 cursor-pointer flex items-center gap-2" style="color:var(--color-orbit-text)" @click="emit('open-file')"> Open File</div>
  <div style="border-top:1px solid var(--color-orbit-border);margin:4px 8px" />
  <div class="px-3 py-1.5 cursor-pointer flex items-center gap-2" style="color:var(--color-orbit-text)" @click="emit('retry')"> Retry</div>
</div></Teleport>
</template>
