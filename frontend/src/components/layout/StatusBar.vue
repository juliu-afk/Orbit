<script setup lang="ts">
// WHY 新建：替代旧的顶部栏 + 零散连接指示器。底部统一状态栏——
// 左：DAG/Chart/Search 入口 icon | 中：当前文件+状态 | 右：熔断灯+连接态+budget
import { computed } from 'vue'
import { useShellStore } from '@/stores/shell'
import { useAgentOpsStore } from '@/stores/agentops'
import type { ConnectionStatus } from '@/composables/useWebSocket'

const props = defineProps<{
  connectionStatus: ConnectionStatus
  budgetLabel?: string
}>()

const emit = defineEmits<{
  (e: 'toggle-dag'): void
  (e: 'toggle-chart'): void
  (e: 'toggle-search'): void
}>()

const shell = useShellStore()
const agentops = useAgentOpsStore()

const connectionLabel = computed(() => {
  switch (props.connectionStatus) {
    case 'connected': return 'orbit ◉'
    case 'connecting': return 'connecting...'
    default: return 'disconnected'
  }
})
</script>

<template>
  <div
    class="status-bar flex items-center justify-between px-3 select-none"
    style="
      height: var(--spacing-statusbar);
      border-top: 1px solid var(--color-orbit-border);
      background: rgba(10, 10, 20, 0.92);
      backdrop-filter: blur(8px);
      font-family: var(--font-mono);
      font-size: 11px;
      color: var(--color-orbit-text-secondary);
    "
  >
    <!-- 左：浮层入口 -->
    <div class="flex items-center gap-3">
      <button
        class="status-btn"
        :class="{ active: shell.showDAG }"
        @click="emit('toggle-dag')"
        title="DAG 任务图"
      >
        ◉ DAG
      </button>
      <button
        class="status-btn"
        :class="{ active: shell.showChart }"
        @click="emit('toggle-chart')"
        title="Token 图表"
      >
        📊 Charts
      </button>
      <button
        class="status-btn"
        :class="{ active: shell.showSearch }"
        @click="emit('toggle-search')"
        title="搜索"
      >
        🔍 Search
      </button>
    </div>

    <!-- 中：当前文件 + 状态 -->
    <div class="flex items-center gap-2">
      <template v-if="shell.selectedFile">
        <span>{{ shell.selectedFile }}</span>
        <span class="text-[var(--color-orbit-accent)]">✓</span>
      </template>
      <template v-else>
        <span class="text-[var(--color-orbit-text-muted)]">ready</span>
      </template>
    </div>

    <!-- 右：熔断灯 + 连接态 + budget -->
    <div class="flex items-center gap-3">
      <!-- 熔断状态灯 -->
      <span
        v-if="agentops.metrics?.circuit_breaker_state"
        class="flex items-center gap-1"
      >
        <span
          v-for="(_state, name) in agentops.metrics.circuit_breaker_state"
          :key="name"
          class="status-dot"
          :class="_state === 0 ? 'connected' : _state === 2 ? 'connecting' : 'disconnected'"
          :title="`${name}: ${
            _state === 0 ? 'CLOSED' : _state === 1 ? 'OPEN' : 'HALF_OPEN'
          }`"
        />
      </span>

      <span class="flex items-center gap-1">
        <span class="status-dot" :class="connectionStatus" />
        {{ connectionLabel }}
      </span>

      <span v-if="budgetLabel" style="color: var(--color-orbit-info);">{{ budgetLabel }}</span>
    </div>
  </div>
</template>

<style scoped>
.status-btn {
  background: none;
  border: none;
  color: var(--color-orbit-text-secondary);
  font-family: var(--font-mono);
  font-size: 11px;
  cursor: pointer;
  padding: 2px 6px;
  border-radius: 3px;
  transition: color 0.15s, background 0.15s;
}
.status-btn:hover {
  color: var(--color-orbit-text);
  background: var(--color-orbit-surface-hover);
}
.status-btn.active {
  color: var(--color-orbit-accent);
}
</style>
