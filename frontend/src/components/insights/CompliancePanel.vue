<!-- 合规检查面板 (Phase 3.2) -->
<template>
  <div class="compliance-panel">
    <div class="comp-header">Compliance</div>
    <div v-if="violations.length" class="comp-list">
      <div v-for="(v, i) in violations" :key="i" class="comp-item" :class="'sev-' + v.severity">
        <span class="comp-icon">{{ v.severity === 'warning' ? '⚠' : 'ℹ' }}</span>
        <span class="comp-file">{{ v.file.split('/').pop() }}:{{ v.line }}</span>
        <span class="comp-msg">{{ v.message }}</span>
      </div>
    </div>
    <div v-else class="comp-none">No violations found</div>
  </div>
</template>

<script setup lang="ts">
interface Violation { file: string; line: number; rule: string; message: string; severity: string }
defineProps<{ violations: Violation[] }>()
</script>

<style scoped>
.compliance-panel { padding: 8px; }
.comp-header { font-weight: 600; font-size: 13px; margin-bottom: 8px; }
.comp-list { max-height: 250px; overflow-y: auto; }
.comp-item { display: flex; align-items: center; gap: 6px; padding: 2px 0; font-size: 13px; }
.comp-icon { width: 16px; text-align: center; }
.sev-warning .comp-icon { color: #e6a23c; }
.comp-file { color: var(--el-color-primary); flex-shrink: 0; }
.comp-msg { color: var(--el-text-color-secondary); }
.comp-none { padding: 12px; color: var(--el-text-color-secondary); }
</style>
