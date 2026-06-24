<!-- 驾驶舱主视图：Session 为顶栏 → 指标 → 内容区 → 底部信息 (Session PR #3) -->
<template>
  <div class="dashboard">
    <div class="dashboard-top">
      <!-- WS 连接状态灯 -->
      <span class="connection-dot" :class="`dot--${ws.connectionStatus.value}`" />
      <span class="connection-label">
        {{ ws.connectionStatus.value === 'connected' ? '已连接' :
           ws.connectionStatus.value === 'connecting' ? '连接中...' : '已断开' }}
      </span>
      <!-- Session 栏 -->
      <SessionBar class="session-bar" @new-session="showNewDialog = true" />
    </div>

    <ConnectionOverlay
      v-if="ws.retryCount.value >= ws.maxRetries"
      @reconnect="handleReconnect"
    />

    <!-- 无 Session 引导页 -->
    <div v-if="!session.currentSessionId" class="welcome">
      <el-empty description="选择一个项目开始工作" :image-size="80">
        <el-button type="primary" @click="showNewDialog = true">
          打开或新建项目
        </el-button>
      </el-empty>
    </div>

    <!-- Session 工作台 -->
    <template v-else>
      <!-- 指标卡片行 -->
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

      <!-- 熔断器指示灯 -->
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

      <!-- 主内容区——左右分栏 -->
      <div class="content-row">
        <!-- 左栏：DAG + 防幻觉 + Token 趋势 -->
        <div class="left-panel">
          <el-card shadow="never" class="panel-card">
            <template #header>DAG 任务流</template>
            <DagCanvas />
          </el-card>
          <el-card shadow="never" class="panel-card">
            <template #header>Token 消耗趋势</template>
            <TokenChart :data-points="tokenPoints" />
          </el-card>
          <el-card shadow="never" class="panel-card">
            <template #header>防幻觉分层拦截</template>
            <div ref="hallucinationChartRef" class="mini-chart" />
          </el-card>
        </div>

        <!-- 右栏：聊天 -->
        <div class="right-panel">
          <ChatPanel />
        </div>
      </div>

      <!-- 底部：告警 + 健康 -->
      <div class="bottom-row">
        <el-card shadow="never" class="panel-card alert-card">
          <template #header>
            活跃告警
            <el-tag v-if="agentOpsStore.alerts.length === 0" size="small" type="success" style="margin-left:8px">无</el-tag>
            <el-tag v-else size="small" type="danger" style="margin-left:8px">{{ agentOpsStore.alerts.length }}</el-tag>
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
      </div>
    </template>

    <!-- 新建 Session 弹窗 -->
    <NewSessionDialog v-model:visible="showNewDialog" @confirmed="onSessionCreated" />

    <!-- 跨项目警告 -->
    <CrossProjectWarning v-if="chatStore.crossProjectWarning" />
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { useWebSocket } from '@/composables/useWebSocket'
import { useSessionStore } from '@/stores/session'
import { useAgentOpsStore } from '@/stores/agentops'
import { useChatStore } from '@/stores/chat'
import type { TokenPoint, WsMessage } from '@/types/dashboard'
import SessionBar from '@/components/layout/SessionBar.vue'
import ConnectionOverlay from '@/components/common/ConnectionOverlay.vue'
import TokenChart from '@/components/charts/TokenChart.vue'
import MetricsCard from '@/components/metrics/MetricsCard.vue'
import CircuitBreakerLight from '@/components/metrics/CircuitBreakerLight.vue'
import HealthPanel from '@/components/metrics/HealthPanel.vue'
import DagCanvas from '@/components/dag/DagCanvas.vue'
import ChatPanel from '@/components/chat/ChatPanel.vue'
import NewSessionDialog from '@/components/layout/NewSessionDialog.vue'
import CrossProjectWarning from '@/components/chat/CrossProjectWarning.vue'

const ws = useWebSocket()
const session = useSessionStore()
const agentOpsStore = useAgentOpsStore()
const chatStore = useChatStore()

const showNewDialog = ref(false)
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
      // WHY touch: 聊天活动更新 session updated_at
      if (session.currentSessionId) {
        session.currentSessionId  // keep session active in store
      }
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

async function onSessionCreated() {
  // Session 创建完成后，恢复聊天消息、刷新指标
  if (session.messages.length > 0) {
    chatStore.restoreMessages(session.messages.map(m => ({
      role: m.role,
      content: m.content,
      created_at: m.created_at,
    })))
  }
  agentOpsStore.fetchAll()
}

// Session PR #3: 切换 Session 时同步消息 + 刷新指标
watch(
  () => session.currentSessionId,
  (newId) => {
    if (newId && session.messages.length > 0) {
      chatStore.restoreMessages(session.messages.map(m => ({
        role: m.role,
        content: m.content,
        created_at: m.created_at,
      })))
    } else if (newId) {
      chatStore.reset()
    }
    tokenPoints.value = []
    agentOpsStore.fetchAll()
    // session ????? chat WS
    if (newId) {
      chatStore.connectChatWs(newId, session.currentProjectName)
    }
  }
)

onMounted(async () => {
  ws.connect(getWsUrl())
  // 先拉取历史 Session 列表
  await session.fetchSessions()
  // 如果有活跃 Session，自动恢复最后一个
  const active = session.sessions.filter(s => s.status === 'active')
  if (active.length > 0) {
    await session.switchToSession(active[0].session_id)
    chatStore.restoreMessages(session.messages.map(m => ({
      role: m.role,
      content: m.content,
      created_at: m.created_at,
    })))
  }
  agentOpsStore.startPolling()
  // ?? chat WS????? Agent???? session ???
  if (session.currentSessionId) {
    chatStore.connectChatWs(session.currentSessionId, session.currentProjectName)
  }
})

onUnmounted(() => {
  ws.disconnect()
  chatStore.disconnect()
  agentOpsStore.reset()
})
</script>

<style scoped>
.dashboard {
  min-height: 100vh;
  background: #0a0a14;
  color: #e0e0e0;
}
.dashboard-top {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 12px;
  background: #12122a;
  border-bottom: 1px solid #2a2a4a;
}
.connection-dot {
  width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0;
}
.dot--connected { background: #4caf50; }
.dot--connecting { background: #ff9800; animation: pulse 1s infinite; }
.dot--disconnected { background: #f44336; }
@keyframes pulse { 0%, 100% { opacity: 1; } 50% { opacity: 0.3; } }
.connection-label { font-size: 11px; color: #888; margin-right: 12px; }
.session-bar { flex: 1; }

.welcome {
  display: flex;
  justify-content: center;
  align-items: center;
  min-height: 60vh;
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

.content-row {
  display: flex;
  gap: 12px;
  padding: 0 12px;
  flex-wrap: wrap;
}
.left-panel {
  flex: 1 1 58%;
  min-width: 360px;
}
.right-panel {
  flex: 1 1 38%;
  min-width: 320px;
  display: flex;
  flex-direction: column;
}

.bottom-row {
  display: flex;
  gap: 12px;
  padding: 12px;
  flex-wrap: wrap;
}
.bottom-row .panel-card {
  flex: 1 1 300px;
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
</style>
