<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import { apiGet } from '@/services/api'
const emit = defineEmits<{ (e: 'send', text: string): void; (e: 'navigate-history', d: -1 | 1): void }>()
const inputRef = ref<HTMLTextAreaElement | null>(null)
const inputText = ref('')
// v0.24: 恢复 apiGet fallback——后端 /api/v1/terminal/commands 可用时动态获取
const FALLBACK_CMDS = ['/task', '/review', '/dream', '/search', '/help', '/compose']
const CMDS = ref<string[]>([...FALLBACK_CMDS])
onMounted(async () => { try { const d = await apiGet<{ commands: string[] }>('/api/v1/terminal/commands'); if (d.commands?.length) CMDS.value = d.commands } catch { /* fallback */ } })
const showAC = ref(false)
const acIdx = ref(0)
const filtered = computed(() => {
  if (!inputText.value.startsWith('/') || inputText.value.includes(' ')) return []
  return CMDS.value.filter(c => c.startsWith(inputText.value))
})
// WHY watch: 用户输入 "/" 时自动弹出补全，不需要手动按 Tab 才发现
watch(inputText, (val) => {
  if (val.startsWith('/') && !val.includes(' ') && filtered.value.length > 0) {
    showAC.value = true
    acIdx.value = 0
  } else if (!val.startsWith('/')) {
    showAC.value = false
  }
})
function selectAc(cmd: string) {
  inputText.value = cmd
  showAC.value = false
  inputRef.value?.focus()
}
function onKey(e: KeyboardEvent) {
  if (e.key === 'Enter' && !e.shiftKey) {
    // WHY: 如果补全菜单打开且有选中项，Enter 选中该项而非发送
    if (showAC.value && filtered.value.length > 0) {
      e.preventDefault()
      selectAc(filtered.value[acIdx.value])
      return
    }
    e.preventDefault(); const t = inputText.value.trim(); if (t) { emit('send', t); inputText.value = ''; showAC.value = false }
  }
  if (e.key === 'Tab') { e.preventDefault(); if (filtered.value.length > 0) { if (!showAC.value) { showAC.value = true } else { acIdx.value = (acIdx.value + 1) % filtered.value.length } } }
  if (e.key === 'ArrowUp') {
    if (showAC.value && filtered.value.length > 0) { e.preventDefault(); acIdx.value = (acIdx.value - 1 + filtered.value.length) % filtered.value.length; return }
    if (inputText.value === '') { e.preventDefault(); emit('navigate-history', -1) }
  }
  if (e.key === 'ArrowDown') {
    if (showAC.value && filtered.value.length > 0) { e.preventDefault(); acIdx.value = (acIdx.value + 1) % filtered.value.length; return }
    if (inputText.value === '') { e.preventDefault(); emit('navigate-history', 1) }
  }
  if (e.key === 'Escape') { showAC.value = false }
}
function focus() { inputRef.value?.focus() }
function setText(text: string) { inputText.value = text; inputRef.value?.focus() }
defineExpose({ focus, setText })
</script>
<template>
<div class="input-box" style="position:relative">
  <div class="flex items-start gap-2 px-3 py-2">
    <textarea ref="inputRef" v-model="inputText" class="flex-1 resize-none outline-none" style="background:transparent;border:none;color:var(--color-orbit-text);font-family:var(--font-mono);font-size:13px;line-height:1.6;caret-color:var(--color-orbit-accent)" rows="1" placeholder="/help..." @keydown="onKey" />
  </div>
  <!-- WHY: 斜杠命令补全下拉——自动弹出，Tab/方向键选择，Enter 选中 -->
  <div v-if="showAC && filtered.length > 0" class="ac-dropdown">
    <div v-for="(cmd, i) in filtered" :key="cmd" class="ac-item" :class="{ 'ac-active': i === acIdx }" @mousedown.prevent="selectAc(cmd)" @mouseenter="acIdx = i">
      {{ cmd }}
    </div>
  </div>
</div>
</template>
<style scoped>
.ac-dropdown {
  position: absolute; bottom: 100%; left: 0; right: 0;
  background: var(--color-orbit-surface); border: 1px solid var(--color-orbit-border);
  border-radius: 4px; margin: 0 8px 4px; max-height: 180px; overflow-y: auto;
  z-index: 100; font-family: var(--font-mono); font-size: 12px;
}
.ac-item {
  padding: 4px 12px; cursor: pointer; color: var(--color-orbit-text-secondary);
}
.ac-item:hover, .ac-active {
  background: var(--color-orbit-surface-hover); color: var(--color-orbit-text);
}
</style>
