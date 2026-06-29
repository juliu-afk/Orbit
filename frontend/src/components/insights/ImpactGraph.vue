<!-- 影响分析可视化 (Phase 3.1) -->
<template>
  <div class="impact-panel">
    <div class="impact-header">Impact Analysis — "{{ symbol }}"</div>
    <div v-if="nodes.length" class="impact-list">
      <div v-for="n in nodes" :key="n.name" class="impact-node" :class="'level-' + n.level">
        <span class="impact-icon">{{ n.level === 'direct' ? '→' : '··' }}</span>
        <span class="impact-name">{{ n.name }}</span>
        <span v-if="n.callers.length" class="impact-callers">called by: {{ n.callers.join(', ') }}</span>
      </div>
    </div>
    <div v-else class="impact-empty">Select a symbol to analyze</div>
  </div>
</template>

<script setup lang="ts">
interface ImpactNode { name: string; file: string; level: string; callers: string[] }
defineProps<{ symbol: string; nodes: ImpactNode[] }>()
</script>

<style scoped>
.impact-panel { padding: 8px; }
.impact-header { font-weight: 600; font-size: 13px; margin-bottom: 8px; }
.impact-list { max-height: 300px; overflow-y: auto; }
.impact-node { display: flex; align-items: center; gap: 6px; padding: 3px 0; font-size: 13px; }
.impact-icon { color: var(--el-color-primary); width: 20px; text-align: center; }
.impact-name { font-weight: 500; }
.impact-callers { color: var(--el-text-color-secondary); font-size: 12px; }
.impact-empty { padding: 12px; color: var(--el-text-color-secondary); }
</style>
