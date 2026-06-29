<!-- Agent 推理链展示面板 (Phase 2.2) -->
<template>
  <div class="trace-panel">
    <div class="trace-header">Agent Reasoning</div>
    <div v-if="!steps.length" class="trace-empty">No trace data</div>
    <el-timeline v-else>
      <el-timeline-item v-for="s in steps" :key="s.step" :timestamp="s.role" :type="s.type" placement="top">
        <div class="trace-step">{{ s.summary }}</div>
        <el-button v-if="s.detail" size="small" text @click="expanded = expanded === s.step ? null : s.step">
          {{ expanded === s.step ? 'Collapse' : 'Details' }}
        </el-button>
        <div v-if="expanded === s.step" class="trace-detail"><pre>{{ s.detail }}</pre></div>
      </el-timeline-item>
    </el-timeline>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'

interface TraceStep { step: number; role: string; summary: string; detail?: string; type: 'primary'|'success'|'warning'|'danger' }
defineProps<{ steps: TraceStep[] }>()
const expanded = ref<number | null>(null)
</script>

<style scoped>
.trace-panel { padding: 8px; }
.trace-header { font-weight: 600; font-size: 13px; margin-bottom: 8px; }
.trace-empty { padding: 12px; color: var(--el-text-color-secondary); font-size: 13px; }
.trace-step { font-size: 13px; }
.trace-detail { margin-top: 4px; max-height: 200px; overflow: auto; }
.trace-detail pre { font-size: 12px; white-space: pre-wrap; word-break: break-all; }
</style>
