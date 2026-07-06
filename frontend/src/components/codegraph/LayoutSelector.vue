<!-- 布局选择器——cose / breadthfirst / concentric 三种布局。 -->
<script setup lang="ts">
import { useCodeGraphStore } from '@/stores/codegraph'

const store = useCodeGraphStore()

const layouts = [
  { key: 'cose', label: '力导向', desc: '适合探索未知依赖结构' },
  { key: 'breadthfirst', label: '层级', desc: '适合有向依赖（导入层次）' },
  { key: 'concentric', label: '同心圆', desc: '按度数排列中心节点' },
]
</script>

<template>
  <div class="layout-selector">
    <label class="layout-label">布局</label>
    <select v-model="store.activeLayout" class="layout-select">
      <option v-for="l in layouts" :key="l.key" :value="l.key" :title="l.desc">
        {{ l.label }}
      </option>
    </select>
  </div>
</template>

<style scoped>
.layout-selector {
  display: flex; align-items: center; gap: 6px;
  font-family: var(--font-mono); font-size: 12px;
}
.layout-label {
  color: var(--color-orbit-text-muted); white-space: nowrap;
}
.layout-select {
  background: rgba(255,255,255,.06); border: 1px solid var(--color-orbit-border);
  border-radius: 4px; color: var(--color-orbit-text);
  padding: 4px 8px; font-family: inherit; font-size: inherit; cursor: pointer;
  outline: none;
}
.layout-select:focus { border-color: var(--color-orbit-accent); }
.layout-select option { background: #1a1a2e; color: #e0e0e0; }
</style>
