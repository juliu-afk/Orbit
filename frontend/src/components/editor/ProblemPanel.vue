<!-- 问题面板——L4 mypy 诊断列表 -->
<template>
  <div class="problem-panel">
    <div v-if="!diagnostics.length" class="no-problems">
      <span>✅ 无诊断问题</span>
    </div>
    <div
      v-for="(d, i) in diagnostics"
      :key="i"
      class="problem-item"
      :class="`severity-${d.severity}`"
      @click="$emit('click', d)"
    >
      <span class="severity-icon">
        {{ d.severity === 'error' ? '🔴' : d.severity === 'warning' ? '🟡' : 'ℹ️' }}
      </span>
      <span class="problem-file">{{ d.filePath.split('/').pop() }}:{{ d.line }}</span>
      <span class="problem-message">{{ d.message }}</span>
      <span v-if="d.ruleId" class="problem-rule">{{ d.ruleId }}</span>
    </div>
  </div>
</template>

<script setup lang="ts">
import type { Diagnostic } from '@/stores/diagnostics'

defineProps<{
  diagnostics: Diagnostic[]
}>()

defineEmits<{
  (e: 'click', d: Diagnostic): void
}>()
</script>

<style scoped>
.problem-panel { padding: 4px 0; }
.no-problems {
  text-align: center;
  padding: 24px;
  color: var(--el-text-color-secondary);
  font-size: 14px;
}
.problem-item {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 3px 12px;
  font-size: 13px;
  cursor: pointer;
}
.problem-item:hover { background: var(--el-fill-color-light); }
.severity-icon { flex-shrink: 0; font-size: 12px; }
.problem-file { color: var(--el-text-color-secondary); flex-shrink: 0; }
.problem-message { flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.problem-rule {
  font-size: 11px;
  color: var(--el-text-color-placeholder);
  flex-shrink: 0;
}
</style>
