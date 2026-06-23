<!-- 驾驶舱主视图：4 标签页 (监控/聊天/运维/资源) + 全局状态栏 -->
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

    <el-tabs v-model="activeTab" class="dashboard-tabs" type="border-card">
      <!-- ── 监控 ──────────────────────────────── -->
      <el-tab-pane label="监控" name="monitor">
        <!-- F1: AgentOps 指标卡片行 -->
        <div class="metrics-row">
          <MetricsCard
            title="任务成功率"
            :value="successRate"
            unit="%"
            :loading="agentOpsStore.loading"
          />
          <MetricsCard
            title="活跃任务"
            :value="agentOpsStore.metrics?.active_tasks ?? null"
            :loading="agentOpsStore.loading"
          />
          <MetricsCard
            title="Token 消耗"
            :value="totalTokens"
            :loading="agentOpsStore.loading"
          />
          <MetricsCard
            title="防幻觉拦截"
            :value="totalIntercepted"
            :loading="agentOpsStore.loading"
          />
        </div>

        <!-- F1: 熔断器指示灯 -->
        <div class="cb-row">
          <CircuitBreakerLight
            name="ResourceGuard"
            :state="agentOpsStore.metrics?.circuit_breaker_state?.resource_guard ?? -1"
          />
          <CircuitBreakerLight
            name="Z3"
            :state="agentOpsStore.metrics?.circuit_breaker_state?.z3 ?? -1"
          />
          <CircuitBreakerLight
            name="Sandbox"
            :state="agentOpsStore.metrics?.circuit_breaker_state?.sandbox ?? -1"
          />
        </div>

        <el-row :gutter="12" class="dashboard-grid">
          <!-- F1: Token 图 + 合规图 -->
          <el-col :xs="24" :lg="14">
            <el-card shadow="never" class="panel-card">
              <template #header>Token 消耗趋势</template>
              <TokenChart :data-points="tokenPoints" />
            </el-card>
            <el-card shadow="never" class="panel-card">
              <template #header>防幻觉 L1-L9 拦截率</template>
              <div ref="hallucinationChartRef" class="mini-chart"></div>
            </el-card>
          </el-col>

          <!-- F1: 告警列表 + 健康 -->
          <el-col :xs="24" :lg="10">
            <el-card shadow="never" class="panel-card alert-card">
              <template #header>
                活跃告警
                <el-tag v-if="agentOpsStore.alerts.length === 0" size="small" type="success" style="margin-left:8px">
                  无
                </el-tag>
                <el-tag v-else size="small" type="danger" style="margin-left:8px">
                  {{ agentOpsStore.alerts.length }}
                </el-tag>
              </template>
              <div v-if="agentOpsStore.alerts.length === 0" class="empty-hint">✅ 无活跃告警</div>
              <div v-else class="alert-list">
                <div
                  v-for="a in agentOpsStore.alerts"
                  :key="a.name"
                  class="alert-item"
                  :class="`alert-item--${a.severity}`"
                >
                  <span class="alert-item__name">{{ a.name }}</span>
                  <span class="alert-item__msg">{{ a.message }}</span>
                </div>
              </div>
            </el-card>

            <el-card shadow="never" class="panel-card">
              <template #header>组件健康</template>
              <HealthPanel
                :components="agentOpsStore.health"
                :overall="agentOpsStore.overallHealth"
              />
            </el-card>
          </el-col>
        </el-row>
      </el-tab-pane>

      <!-- ── 聊天 ───────────────────────────── -->
      <el-tab-pane label="聊天" name="chat">
        <ChatPanel />
      </el-tab-pane>

      <!-- ── 运维 ───────────────────────────── -->
      <el-tab-pane label="运维" name="ops">
        <OpsPanel />
      </el-tab-pane>

      <!-- ── 资源 ───────────────────────────── -->
      <el-tab-pane label="资源" name="resources">
        <ResourcePanel />
      </el-tab-pane>
    </el-tabs>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { useWebSocket } from '@/composables/useWebSocket'
import { useDashboardStore } from '@/stores/dashboard'
import { useAgentOpsStore } from '@/stores/agentops'
import type { TokenPoint, WsMessage } from '@/types/dashboard'
import GlobalStatusBar from '@/components/layout/GlobalStatusBar.vue'
import ConnectionOverlay from '@/components/common/ConnectionOverlay.vue'
import TokenChart from '@/components/charts/TokenChart.vue'
import MetricsCard from '@/components/metrics/MetricsCard.vue'
import CircuitBreakerLight from '@/components/metrics/CircuitBreakerLight.vue'
import HealthPanel from '@/components/metrics/HealthPanel.vue'
import ChatPanel from '@/components/chat/ChatPanel.vue'
import OpsPanel from '@/components/ops/OpsPanel.vue'
import ResourcePanel from '@/components/resources/ResourcePanel.vue'

const ws = useWebSocket()
const dashboardStore = useDashboardStore()
const agentOpsStore = useAgentOpsStore()

const activeTab = ref('monitor')
const hallucinationChartRef = ref<HTMLElement | null>(null)
const tokenPoints = ref<TokenPoint[]>([])
const MAX_TOKEN_POINTS = 100

// ── 计算属性 ──────────────────────────────────────

const successRate = computed(() => {
  const m = agentOpsStore.metrics
  if (!m) return null
  const success = m.tasks_total?.success ?? 0
  const total = (m.tasks_total?.success ?? 0) + (m.tasks_total?.failed ?? 0)
  if (total === 0) return 100
  return Math.round((success / total) * 100)
})

const totalTokens = computed(() => {
  const m = agentOpsStore.metrics
  if (!m) return null
  return (m.llm_tokens_total?.input ?? 0) + (m.llm_tokens_total?.output ?? 0)
})

const totalIntercepted = computed(() => {
  const m = agentOpsStore.metrics
  if (!m) return null
  const h = m.hallucination_intercepted_total ?? {}
  return Object.values(h).reduce((a, b) => a + b, 0)
})

// ── WS 消息路由 ──────────────────────────────────

ws.setMessageHandler((msg: WsMessage) => {
  dashboardStore.touch()

  switch (msg.type) {
    case 'metrics:snapshot':
      agentOpsStore.handleWsEvent('metrics:snapshot', msg.payload)
      break
    case 'agentops:alert':
      agentOpsStore.handleWsEvent('agentops:alert', msg.payload)
      break
    case 'token:update': {
      const tp: TokenPoint = {
        timestamp: (msg.timestamp as string) || new Date().toISOString(),
        prompt_tokens: (msg.payload.prompt_tokens as number) || 0,
        completion_tokens: (msg.payload.completion_tokens as number) || 0,
        total_tokens: (msg.payload.total_tokens as number) || 0,
      }
      tokenPoints.value.push(tp)
      if (tokenPoints.value.length > MAX_TOKEN_POINTS) tokenPoints.value.shift()
      break
    }
  }
})

function handleReconnect() {
  ws.connect(getWsUrl())
}

function getWsUrl(): string {
  const protocol = location.protocol === 'https:' ? 'wss:' : 'ws:'
  return `${protocol}//${location.host}/ws/dashboard`
}

onMounted(() => {
  ws.connect(getWsUrl())
  agentOpsStore.startPolling()
})

onUnmounted(() => {
  ws.disconnect()
  agentOpsStore.reset()
})
</script>

<style scoped>
.dashboard {
  min-height: 100vh;
  background: #0a0a14;
  color: #e0e0e0;
}
.dashboard-tabs {
  margin: 12px;
  background: #0a0a14;
  border: 1px solid #2a2a4a;
}
.dashboard-tabs :deep(.el-tabs__header) {
  background: #12122a;
  border-bottom: 1px solid #2a2a4a;
}
.dashboard-tabs :deep(.el-tabs__item) {
  color: #8888aa;
}
.dashboard-tabs :deep(.el-tabs__item.is-active) {
  color: #4caf50;
}

.metrics-row {
  display: flex;
  gap: 12px;
  padding: 12px;
  flex-wrap: wrap;
}
.cb-row {
  display: flex;
  gap: 12px;
  padding: 0 12px 12px;
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
.panel-card :deep(.el-card__body) { padding: 0; }
.alert-card :deep(.el-card__body) { padding: 0; }

.mini-chart { height: 200px; }

.alert-list { padding: 8px; }
.alert-item {
  padding: 8px 12px;
  border-radius: 4px;
  margin-bottom: 4px;
  display: flex;
  justify-content: space-between;
  font-size: 12px;
}
.alert-item--warning { background: rgba(255, 152, 0, 0.1); border-left: 3px solid #ff9800; }
.alert-item--critical { background: rgba(244, 67, 54, 0.1); border-left: 3px solid #f44336; }
.alert-item__name { font-weight: 600; color: #e0e0e0; }
.alert-item__msg { color: #888; }

.empty-hint { text-align: center; padding: 24px; color: #4caf50; font-size: 14px; }
.placeholder-tab { text-align: center; padding: 60px; color: #666; font-size: 16px; }
</style>
