<!-- 搜索栏——按文件路径/符号名过滤节点。防抖 300ms。 -->
<script setup lang="ts">
import { ref, watch } from 'vue'
import { useCodeGraphStore } from '@/stores/codegraph'

const store = useCodeGraphStore()
const inputValue = ref('')
let debounceTimer: ReturnType<typeof setTimeout> | null = null

function onInput(value: string): void {
  if (debounceTimer) clearTimeout(debounceTimer)
  // WHY 300ms 防抖：Cytoscape 样式批量更新需要重绘，
  // 避免每次按键都触发全图重绘
  debounceTimer = setTimeout(() => {
    store.setSearchQuery(value)
  }, 300)
}

function clearSearch(): void {
  inputValue.value = ''
  store.setSearchQuery('')
}

// 外部清空搜索时同步输入框（如双击空白重置）
watch(() => store.searchQuery, (q) => {
  if (!q) inputValue.value = ''
})
</script>

<template>
  <div class="search-bar">
    <svg class="search-icon" viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2">
      <circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/>
    </svg>
    <input
      v-model="inputValue"
      type="text"
      placeholder="搜索文件或符号…"
      class="search-input"
      @input="onInput(($event.target as HTMLInputElement).value)"
    />
    <button v-if="inputValue" class="clear-btn" @click="clearSearch" title="清除">✕</button>
  </div>
</template>

<style scoped>
.search-bar {
  display: flex; align-items: center; gap: 8px;
  background: rgba(255,255,255,.06); border: 1px solid var(--color-orbit-border);
  border-radius: 6px; padding: 6px 10px;
  font-family: var(--font-mono); font-size: 13px;
}
.search-icon { color: var(--color-orbit-text-muted); flex-shrink: 0; }
.search-input {
  flex: 1; background: none; border: none; color: var(--color-orbit-text);
  outline: none; font-family: inherit; font-size: inherit;
}
.search-input::placeholder { color: var(--color-orbit-text-muted); }
.clear-btn {
  background: none; border: none; color: var(--color-orbit-text-muted);
  cursor: pointer; font-size: 12px; padding: 0 2px;
}
.clear-btn:hover { color: var(--color-orbit-text); }
</style>
