<!-- 风险评分面板 (Phase 3.1) -->
<template>
  <div class="risk-panel">
    <div class="risk-header">Risk Scores</div>
    <div v-for="r in risks" :key="r.file" class="risk-item" :class="'level-' + r.level">
      <span class="risk-file">{{ r.file.split('/').pop() }}</span>
      <el-progress :percentage="r.score" :color="r.level === 'high' ? '#f56c6c' : r.level === 'medium' ? '#e6a23c' : '#67c23a'" :stroke-width="8" style="flex:1;margin:0 8px" />
      <el-tag v-for="f in r.factors" :key="f" size="small">{{ f }}</el-tag>
    </div>
  </div>
</template>

<script setup lang="ts">
interface RiskItem { file: string; score: number; level: string; factors: string[] }
defineProps<{ risks: RiskItem[] }>()
</script>

<style scoped>
.risk-panel { padding: 8px; }
.risk-header { font-weight: 600; font-size: 13px; margin-bottom: 8px; }
.risk-item { display: flex; align-items: center; gap: 4px; padding: 4px 0; font-size: 13px; }
.risk-file { width: 120px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; flex-shrink: 0; }
</style>
