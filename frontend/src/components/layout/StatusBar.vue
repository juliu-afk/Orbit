<script setup lang="ts">
import { computed } from 'vue'
import { useShellStore } from '@/stores/shell'
import { usePeakStore } from '@/stores/peak'
import type { ConnectionStatus } from '@/composables/useWebSocket'

const props = defineProps<{ connectionStatus: ConnectionStatus; budgetLabel?: string }>()
const emit = defineEmits<{ (e: 'toggle-dag'): void; (e: 'toggle-chart'): void; (e: 'toggle-search'): void; (e: 'toggle-schedule'): void }>()
const shell = useShellStore()
const peak = usePeakStore()

const connectionLabel = computed(() => {
  switch (props.connectionStatus) {
    case 'connected': return 'orbit'
    case 'connecting': return 'connecting...'
    default: return 'disconnected'
  }
})
</script>

<template>
<div class="status-bar flex items-center justify-between px-3 select-none" style="height:28px;border-top:1px solid var(--color-orbit-border);background:rgba(10,10,20,0.92);font-family:var(--font-mono);font-size:11px;color:var(--color-orbit-text-secondary)">
  <div class="flex items-center gap-3">
    <button class="status-btn" :class="{ active: shell.showDAG }" @click="emit('toggle-dag')" style="background:none;border:none;color:var(--color-orbit-text-secondary);cursor:pointer;font-family:var(--font-mono);font-size:11px;padding:2px 6px;border-radius:3px"> DAG</button>
    <button class="status-btn" :class="{ active: shell.showChart }" @click="emit('toggle-chart')" style="background:none;border:none;color:var(--color-orbit-text-secondary);cursor:pointer;font-family:var(--font-mono);font-size:11px;padding:2px 6px;border-radius:3px"> Charts</button>
    <button class="status-btn" :class="{ active: shell.showSearch }" @click="emit('toggle-search')" style="background:none;border:none;color:var(--color-orbit-text-secondary);cursor:pointer;font-family:var(--font-mono);font-size:11px;padding:2px 6px;border-radius:3px"> Search</button>
    <button class="status-btn" :class="{ active: shell.showSchedule }" @click="emit('toggle-schedule')"><span class="peak-dot" :class="{ peak: peak.isPeak }" />Schedule<span v-if="peak.queuedCount > 0" class="queue-badge">{{ peak.queuedCount }}</span></button>
  </div>
  <div class="flex items-center gap-2">
    <span v-if="shell.selectedFile">{{ shell.selectedFile }} </span>
    <span v-else style="color:var(--color-orbit-text-muted)">ready</span>
  </div>
  <div class="flex items-center gap-3">
    <span class="flex items-center gap-1"><span class="status-dot" :class="connectionStatus"/>{{ connectionLabel }}</span>
  </div>
</div>
</template>
<style scoped>
.status-btn{background:none;border:none;color:var(--color-orbit-text-secondary);cursor:pointer;font-family:var(--font-mono);font-size:11px;padding:2px 6px;border-radius:3px;display:flex;align-items:center;gap:4px}
.status-btn:hover{background:rgba(255,255,255,.06)}
.status-btn.active{background:rgba(255,255,255,.1);color:#e0e0e0}
.peak-dot{width:6px;height:6px;border-radius:50%;background:#67c23a}
.peak-dot.peak{background:#e6a23c}
.queue-badge{background:#e6a23c;color:#1a1a2e;font-size:10px;padding:0 4px;border-radius:3px;font-weight:600}
</style>
