<!-- 顶部全局状态栏：连接状态 / 当前任务 / 最后更新时间 -->
<template>
  <div class="status-bar">
    <div class="status-left">
      <span class="status-dot" :class="statusClass" />
      <span class="status-text">{{ statusText }}</span>
      <el-divider direction="vertical" />
      <span>任务: <code>{{ taskId || '—' }}</code></span>
    </div>
    <div class="status-right">
      <span>最后更新: {{ lastUpdateText }}</span>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { ConnectionStatus } from '@/composables/useWebSocket'

const props = defineProps<{
  connectionStatus: ConnectionStatus
  taskId: string | null
  lastUpdateTime: number | null
}>()

const statusClass = computed(() => ({
  'status-connected': props.connectionStatus === 'connected',
  'status-connecting': props.connectionStatus === 'connecting',
  'status-disconnected': props.connectionStatus === 'disconnected',
}))

const statusText = computed(() => {
  switch (props.connectionStatus) {
    case 'connected': return '已连接'
    case 'connecting': return '连接中...'
    case 'disconnected': return '已断开'
  }
})

const lastUpdateText = computed(() => {
  if (!props.lastUpdateTime) return '—'
  return new Date(props.lastUpdateTime).toLocaleTimeString('zh-CN')
})
</script>

<style scoped>
.status-bar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  height: 36px;
  padding: 0 16px;
  background: #1a1a2e;
  color: #e0e0e0;
  font-size: 13px;
  border-bottom: 1px solid #303050;
}
.status-left, .status-right { display: flex; align-items: center; gap: 8px; }
.status-dot {
  width: 8px; height: 8px; border-radius: 50%; display: inline-block;
}
.status-connected { background: #67C23A; }
.status-connecting { background: #E6A23C; animation: pulse 1s infinite; }
.status-disconnected { background: #F56C6C; animation: pulse 0.5s infinite; }
@keyframes pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.3; }
}
code { color: #409EFF; font-size: 12px; }
</style>
