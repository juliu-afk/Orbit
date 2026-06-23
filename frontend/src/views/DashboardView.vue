<!-- 驾驶舱主视图：全局状态栏 + DAG 拓扑 + Token 图 + 告警列表 -->
<template>
  <div class="dashboard">
    <GlobalStatusBar
      :connection-status="ws.connectionStatus.value"
      :task-id="dashboardStore.currentTaskId"
      :last-update-time="dashboardStore.lastUpdateTime"
    />

    <ConnectionOverlay
      v-if="ws.retryCount.value >= ws.maxRetries"
      @reconnect="handleReconnect"
    />

    <el-row :gutter="12" class="dashboard-grid">
      <!-- 左栏：DAG 拓扑图 -->
      <el-col :xs="24" :lg="14">
        <el-card shadow="never" class="panel-card">
          <template #header>
            <span>任务拓扑 (DAG)</span>
            <el-tag
              v-if="dashboardStore.currentTaskId"
              size="small"
              :type="taskStateTagType"
              style="margin-left: 8px"
            >
              {{ taskStore.taskState }}
            </el-tag>
          </template>
          <DagCanvas />
        </el-card>
      </el-col>

      <!-- 右栏：Token 图 + 告警列表 -->
      <el-col :xs="24" :lg="10">
        <el-card shadow="never" class="panel-card">
          <template #header>Token 消耗</template>
          <TokenChart :data-points="tokenPoints" />
        </el-card>

        <el-card shadow="never" class="panel-card alert-card">
          <AlertList />
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { useWebSocket } from '@/composables/useWebSocket'
import { useDashboardStore } from '@/stores/dashboard'
import { useTaskStore } from '@/stores/task'
import { useAlertStore } from '@/stores/alert'
import type { Alert, TokenPoint, WsMessage } from '@/types/dashboard'
import GlobalStatusBar from '@/components/layout/GlobalStatusBar.vue'
import ConnectionOverlay from '@/components/common/ConnectionOverlay.vue'
import DagCanvas from '@/components/dag/DagCanvas.vue'
import TokenChart from '@/components/charts/TokenChart.vue'
import AlertList from '@/components/alerts/AlertList.vue'

const ws = useWebSocket()
const dashboardStore = useDashboardStore()
const taskStore = useTaskStore()
const alertStore = useAlertStore()

// Token 数据：简单 composable ref，不建 Pinia Store
const tokenPoints = ref<TokenPoint[]>([])
const MAX_TOKEN_POINTS = 100

// WS 消息路由：分发到各 Store
ws.setMessageHandler((msg: WsMessage) => {
  dashboardStore.touch()

  switch (msg.type) {
    case 'task:update':
      taskStore.handleTaskUpdate(msg.payload)
      break
    case 'token:update': {
      const tp: TokenPoint = {
        timestamp: (msg.timestamp as string) || new Date().toISOString(),
        prompt_tokens: (msg.payload.prompt_tokens as number) || 0,
        completion_tokens: (msg.payload.completion_tokens as number) || 0,
        total_tokens: (msg.payload.total_tokens as number) || 0,
      }
      tokenPoints.value.push(tp)
      if (tokenPoints.value.length > MAX_TOKEN_POINTS) {
        tokenPoints.value.shift()
      }
      break
    }
    case 'alert:new': {
      const alert: Alert = {
        task_id: (msg.task_id as string) || '',
        level: (msg.payload.level as string) || 'unknown',
        severity: (msg.payload.severity as 'warning' | 'critical') || 'warning',
        message: (msg.payload.message as string) || '',
        timestamp: (msg.payload.timestamp as string) || new Date().toISOString(),
      }
      alertStore.addAlert(alert)
      break
    }
  }
})

// 任务状态 tag 颜色
const taskStateTagType = computed(() => {
  switch (taskStore.taskState) {
    case 'DONE': return 'success'
    case 'FAILED': return 'danger'
    case 'CANCELLED': return 'info'
    default: return 'warning'
  }
})

function handleReconnect() {
  ws.connect(getWsUrl())
}

function getWsUrl(): string {
  // 开发环境走 Vite proxy，生产环境同源
  const protocol = location.protocol === 'https:' ? 'wss:' : 'ws:'
  return `${protocol}//${location.host}/ws/dashboard`
}

onMounted(() => {
  ws.connect(getWsUrl())
  // MVP：自动订阅一个 Demo 任务（后续版本从任务列表选择）
  // dashboardStore.setTask('demo-task-id')
  // ws.subscribe('demo-task-id')
})

onUnmounted(() => {
  ws.disconnect()
  taskStore.reset()
  alertStore.clearAlerts()
})
</script>

<style scoped>
.dashboard {
  min-height: 100vh;
  background: #0a0a14;
  color: #e0e0e0;
}
.dashboard-grid {
  padding: 12px;
  margin: 0 !important;
}
.panel-card {
  margin-bottom: 12px;
  background: #12122a;
  border: 1px solid #2a2a4a;
}
.panel-card :deep(.el-card__header) {
  border-bottom: 1px solid #2a2a4a;
  color: #c0c0c0;
  font-size: 14px;
  font-weight: 500;
  padding: 10px 16px;
}
.panel-card :deep(.el-card__body) {
  padding: 0;
}
.alert-card :deep(.el-card__body) {
  padding: 0;
}
</style>
