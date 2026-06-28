<!-- 驾驶舱：Session顶栏 → 聊天主区域 + 右侧摘要 → 抽屉详情 -->
<template>
  <div class="dashboard">
    <div class="dashboard-top" data-tauri-drag-region>
      <span class="connection-dot" :class="`dot--${ws.connectionStatus.value}`" />
      <span class="connection-label">
        {{ ws.connectionStatus.value === 'connected' ? '已连接' :
           ws.connectionStatus.value === 'connecting' ? '连接中...' : '已断开' }}
      </span>
      <SessionBar class="session-bar" @new-session="showNewDialog = true" />
    </div>

    <ConnectionOverlay
      v-if="ws.retryCount.value >= ws.maxRetries"
      @reconnect="handleReconnect"
    />

    <!-- 无 Session 引导 -->
    <div v-if="!session.currentSessionId" class="welcome">
      <el-empty description="选择一个项目开始工作" :image-size="80">
        <el-button type="primary" @click="showNewDialog = true">打开或新建项目</el-button>
      </el-empty>
    </div>

    <!-- Session 工作台 -->
    <div v-else class="workspace">
      <!-- 聊天主区域 -->
      <div class="chat-col">
        <ChatPanel />
      </div>

      <!-- 右侧摘要 -->
      <div class="aside-col">
        <div class="aside-item">
          <span class="aside-label">活跃任务</span>
          <span class="aside-val">{{ agentOpsStore.metrics?.active_tasks ?? '---' }}</span>
        </div>
        <div class="aside-item">
          <span class="aside-label">Token 消耗</span>
          <span class="aside-val">{{ totalTokens ?? '---' }}</span>
        </div>
        <div class="aside-item">
          <span class="aside-label">防幻觉拦截</span>
          <span class="aside-val">{{ totalIntercepted ?? '---' }}</span>
        </div>
        <div class="aside-item">
          <span class="aside-label">熔断器</span>
          <span class="aside-val aside-cb">
            <CircuitBreakerLight name="RG" :state="agentOpsStore.metrics?.circuit_breaker_state?.resource_guard ?? -1" />
            <CircuitBreakerLight name="Z3" :state="agentOpsStore.metrics?.circuit_breaker_state?.z3 ?? -1" />
            <CircuitBreakerLight name="SB" :state="agentOpsStore.metrics?.circuit_breaker_state?.sandbox ?? -1" />
          </span>
        </div>
        <div v-if="agentOpsStore.alerts.length > 0" class="aside-item aside-item--warn">
          <span class="aside-label">告警</span>
          <span class="aside-val">{{ agentOpsStore.alerts.length }}</span>
        </div>
        <div class="aside-item">
          <span class="aside-label">系统健康</span>
          <span class="aside-val" :class="`health--${agentOpsStore.overallHealth}`">
            {{ agentOpsStore.overallHealth === 'healthy' ? '正常' :
               agentOpsStore.overallHealth === 'degraded' ? '降级' :
               agentOpsStore.overallHealth === 'unhealthy' ? '异常' : '---' }}
          </span>
        </div>

        <el-button size="small" class="aside-detail-btn" @click="composeTrigger?.open()">
          Spec Compose ▸
        </el-button>
        <DreamPanel />
        <el-button size="small" class="aside-detail-btn" @click="showDetail = true">
          详情 ▸
        </el-button>
      </div>
    </div>

    <!-- 抽屉详情 -->
    <el-drawer v-model="showDetail" title="系统详情" direction="rtl" size="480px">
      <TokenChart :data-points="tokenPoints" />
      <el-divider />
      <template v-if="agentOpsStore.alerts.length === 0">
        <p style="color:#4caf50;font-size:13px;padding:0 12px">✅ 无活跃告警</p>
      </template>
      <template v-else>
        <div
          v-for="a in agentOpsStore.alerts"
          :key="a.name"
          class="drawer-alert"
          :class="`drawer-alert--${a.severity}`"
        >
          <span class="drawer-alert__name">{{ a.name }}</span>
          <span class="drawer-alert__msg">{{ a.message }}</span>
        </div>
      </template>
      <el-divider />
      <HealthPanel :components="agentOpsStore.health" :overall="agentOpsStore.overallHealth" />
    </el-drawer>

    <!-- 代码输出弹出——任务 CODING/DONE 时自动打开 -->
    <el-drawer v-model="showCodeDiff" title="Generated Code" direction="rtl" size="520px" @close="handleCloseCodeDiff">
      <CodeDiffPanel v-if="taskStore.codeOutput" :code="taskStore.codeOutput" />
    </el-drawer>

    <ComposeTrigger ref="composeTrigger" />
    <NewSessionDialog v-model:visible="showNewDialog" @confirmed="onSessionCreated" />
    <CrossProjectWarning v-if="chatStore.crossProjectWarning" />
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { useWebSocket } from '@/composables/useWebSocket'
import { useSessionStore } from '@/stores/session'
import { useAgentOpsStore } from '@/stores/agentops'
import { useChatStore } from '@/stores/chat'
import { useTaskStore } from '@/stores/task'
import type { TokenPoint, WsMessage } from '@/types/dashboard'
import SessionBar from '@/components/layout/SessionBar.vue'
import ConnectionOverlay from '@/components/common/ConnectionOverlay.vue'
import TokenChart from '@/components/charts/TokenChart.vue'
import CircuitBreakerLight from '@/components/metrics/CircuitBreakerLight.vue'
import HealthPanel from '@/components/metrics/HealthPanel.vue'
import ChatPanel from '@/components/chat/ChatPanel.vue'
import NewSessionDialog from '@/components/layout/NewSessionDialog.vue'
import CrossProjectWarning from '@/components/chat/CrossProjectWarning.vue'
import CodeDiffPanel from '@/components/chat/CodeDiffPanel.vue'
import ComposeTrigger from '@/components/chat/ComposeTrigger.vue'
import DreamPanel from '@/components/chat/DreamPanel.vue'

const ws = useWebSocket()
const composeTrigger = ref<InstanceType<typeof ComposeTrigger> | null>(null)
const session = useSessionStore()
const agentOpsStore = useAgentOpsStore()
const chatStore = useChatStore()
const taskStore = useTaskStore()

const showNewDialog = ref(false)
const showDetail = ref(false)
const showCodeDiff = ref(false)
const tokenPoints = ref<TokenPoint[]>([])
const MAX_TOKEN_POINTS = 100

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

ws.setMessageHandler((msg: WsMessage) => {
  switch (msg.type) {
    case 'task:update':
      taskStore.handleTaskUpdate(msg.payload as Record<string, unknown>)
      break
    case 'alert:new':
      agentOpsStore.handleWsEvent('alert:new', msg.payload)
      break
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

function handleReconnect() { ws.connect(getWsUrl()) }
function getWsUrl(): string {
  const p = location.protocol === 'https:' ? 'wss:' : 'ws:'
  return `${p}//${location.host}/ws/dashboard`
}

async function onSessionCreated() {
  if (session.messages.length > 0) {
    chatStore.restoreMessages(session.messages.map(m => ({
      role: m.role, content: m.content, created_at: m.created_at,
    })))
  }
  agentOpsStore.fetchAll()
}

// 代码产物就绪 → 自动弹出抽屉
watch(() => taskStore.hasCodeOutput, (show) => {
  if (show) showCodeDiff.value = true
})

function handleCloseCodeDiff() {
  showCodeDiff.value = false
  taskStore.consumeCodeOutput()
}

// Session 切换: 同步消息 + 刷新指标 + 重连 chat WS
watch(() => session.currentSessionId, (newId) => {
  if (newId && session.messages.length > 0) {
    chatStore.restoreMessages(session.messages.map(m => ({
      role: m.role, content: m.content, created_at: m.created_at,
    })))
  } else if (newId) {
    chatStore.reset()
  }
  tokenPoints.value = []
  agentOpsStore.fetchAll()
  if (newId) chatStore.connectChatWs(newId, session.currentProjectName)
})

onMounted(async () => {
  ws.connect(getWsUrl())
  await session.fetchSessions()
  const active = session.sessions.filter(s => s.status === 'active')
  if (active.length > 0) {
    await session.switchToSession(active[0].session_id)
    chatStore.restoreMessages(session.messages.map(m => ({
      role: m.role, content: m.content, created_at: m.created_at,
    })))
  }
  agentOpsStore.startPolling()
  if (session.currentSessionId) {
    chatStore.connectChatWs(session.currentSessionId, session.currentProjectName)
  }
})

onUnmounted(() => {
  ws.disconnect()
  agentOpsStore.reset()
  chatStore.disconnect()
})
</script>

<style scoped>
.dashboard { height: 100vh; overflow: hidden; display: flex; flex-direction: column; background: #0a0a14; color: #e0e0e0; }
.dashboard-top {
  display: flex; align-items: center; gap: 8px;
  padding: 6px 12px; background: #12122a; border-bottom: 1px solid #2a2a4a;
  flex-shrink: 0;
}
.connection-dot { width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0; }
.dot--connected { background: #4caf50; }
.dot--connecting { background: #ff9800; animation: pulse 1s infinite; }
.dot--disconnected { background: #f44336; }
@keyframes pulse { 0%,100%{opacity:1} 50%{opacity:.3} }
.connection-label { font-size: 11px; color: #888; margin-right: 12px; }
.session-bar { flex: 1; }

.welcome { display: flex; justify-content: center; align-items: center; min-height: 60vh; }

/* ── 工作台 ── */
.workspace {
  display: flex;
  flex: 1;
  overflow: hidden;
}
.chat-col {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}
.aside-col {
  width: 220px;
  flex-shrink: 0;
  padding: 12px;
  background: #0f0f1a;
  border-left: 1px solid #2a2a4a;
  display: flex;
  flex-direction: column;
  gap: 2px;
  overflow-y: auto;
}

.aside-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 6px 0;
  border-bottom: 1px solid #1a1a2e;
}
.aside-label { font-size: 12px; color: #888; }
.aside-val { font-size: 14px; font-weight: 600; color: #e0e0e0; }
.aside-cb { display: flex; gap: 4px; }
.aside-item--warn .aside-val { color: #ff9800; }
.health--healthy { color: #4caf50; }
.health--degraded { color: #ff9800; }
.health--unhealthy { color: #f44336; }

.aside-detail-btn {
  margin-top: 8px;
  width: 100%;
}

.aside-section { margin-bottom: 4px; }
.aside-section-title {
  font-size: 10px;
  font-weight: 700;
  color: #666;
  text-transform: uppercase;
  letter-spacing: 1px;
  padding: 4px 0 6px;
}
.aside-tools { display: flex; flex-direction: column; gap: 4px; }
.aside-footer { margin-top: auto; padding-top: 8px; }

/* ── 抽屉 ── */
.drawer-alert {
  padding: 8px 12px; margin: 0 12px 4px; border-radius: 4px;
  display: flex; justify-content: space-between; font-size: 12px;
}
.drawer-alert--warning { background: rgba(255,152,0,.1); border-left: 3px solid #ff9800; }
.drawer-alert--critical { background: rgba(244,67,54,.1); border-left: 3px solid #f44336; }
.drawer-alert__name { font-weight: 600; color: #e0e0e0; }
.drawer-alert__msg { color: #888; }
</style>
