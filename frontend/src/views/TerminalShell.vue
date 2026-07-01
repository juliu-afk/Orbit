<script setup lang="ts">
// WHY 新建：替代 DashboardView.vue + ReviewView.vue——单页面板分屏布局。
// CSS Grid 四区：左文件树 | 中终端聊天 | 右 Agent 信息/Monaco | 底状态栏。
// 不再有路由跳转——面板显隐由 shellStore 控制。
import { onMounted, onUnmounted, watch } from 'vue'
import { useShellStore } from '@/stores/shell'
import { useSessionStore } from '@/stores/session'
import { useAgentOpsStore } from '@/stores/agentops'
import { useChatStore } from '@/stores/chat'
import { useTaskStore } from '@/stores/task'
import { useWebSocket } from '@/composables/useWebSocket'
import StatusBar from '@/components/layout/StatusBar.vue'

import TerminalChat from '@/components/chat/TerminalChat.vue'
import MonacoPanel from '@/components/editor/MonacoPanel.vue'
import AgentInfoPanel from '@/components/resources/AgentInfoPanel.vue'
import DAGDrawer from '@/components/dag/DAGDrawer.vue'
import TokenChartDrawer from '@/components/charts/TokenChartDrawer.vue'
import SearchDrawer from '@/components/editor/SearchDrawer.vue'

const shell = useShellStore()
const session = useSessionStore()
const agentops = useAgentOpsStore()
const chat = useChatStore()
const task = useTaskStore()
const ws = useWebSocket()

// 会话切换时重连 chat WS
watch(() => session.currentSessionId, (newId) => {
  if (newId) {
    chat.connectChatWs(newId, session.currentProjectName || '')
  }
})

// ⌘B / Ctrl+B 切换文件树
function onKeydown(e: KeyboardEvent) {
  if ((e.metaKey || e.ctrlKey) && e.key === 'b') {
    e.preventDefault()
    shell.toggleFileTree()
  }
  if (e.key === 'Escape') {
    shell.closeAllDrawers()
    if (shell.showMonaco) shell.closeFileReview()
  }
}

onMounted(async () => {
  window.addEventListener('keydown', onKeydown)

  // 配置 WS 消息分发——与旧 DashboardView 相同逻辑
  ws.setMessageHandler((msg) => {
    switch (msg.type) {
      case 'task:update':
        task.handleTaskUpdate(msg.payload as Record<string, unknown>)
        break
      case 'metrics:snapshot':
        agentops.handleWsEvent('metrics:snapshot', msg.payload as Record<string, unknown>)
        break
      case 'agentops:alert':
        agentops.handleWsEvent('agentops:alert', msg.payload as Record<string, unknown>)
        break
      default:
        break
    }
  })

  // 连接 WebSocket
  ws.connect(`ws://${window.location.host}/ws/dashboard`)

  // 获取会话列表，自动切换到第一个 active session
  await session.fetchSessions()
  if (!session.currentSessionId && session.sessions.length > 0) {
    await session.switchToSession(session.sessions[0].session_id)
  }

  // 如果有活跃会话，连接 chat WS
  if (session.currentSessionId) {
    chat.connectChatWs(session.currentSessionId, session.currentProjectName || '')
  }

  // 启动 AgentOps 轮询
  agentops.startPolling()
})

onUnmounted(() => {
  window.removeEventListener('keydown', onKeydown)
  ws.disconnect()
  chat.disconnect()
  agentops.stopPolling()
  task.reset()
})
</script>

<template>
  <div
    class="terminal-shell glass"
    :data-filetree-collapsed="!shell.showFileTree"
    @contextmenu.prevent
  >
    <!-- 左：文件树面板 -->
    <aside
      v-show="shell.showFileTree"
      class="panel-left"
      style="border-right: 1px solid var(--color-orbit-border); overflow-y: auto;"
    >
      <div class="p-3 text-xs text-[var(--color-orbit-text-muted)] tracking-wide uppercase">
        Files
      </div>
      <!-- Phase D: FileTreePanel 在此挂载 -->
      <div class="p-3 text-xs text-[var(--color-orbit-text-muted)]">
        文件树——Phase D 实现
      </div>
    </aside>

    <!-- 中：终端聊天面板 -->
    <main class="panel-center flex flex-col overflow-hidden">
      <TerminalChat />
    </main>

    <!-- 右：Agent 信息 / Monaco 面板 -->
    <aside
      class="panel-right"
      style="border-left: 1px solid var(--color-orbit-border); overflow-y: auto;"
    >
      <MonacoPanel v-if="shell.showMonaco" />
      <AgentInfoPanel v-else />
    </aside>

    <!-- 底：状态栏 -->
    <StatusBar
      class="panel-bottom"
      :connection-status="ws.connectionStatus.value"
      @toggle-dag="shell.toggleDAG()"
      @toggle-chart="shell.toggleChart()"
      @toggle-search="shell.toggleSearch()"
    />

    <!-- DAG / Chart / Search 浮层 -->
    <DAGDrawer v-model:show="shell.showDAG" />
    <TokenChartDrawer v-model:show="shell.showChart" />
    <SearchDrawer
      v-model:show="shell.showSearch"
      @open-file="shell.openFileReview"
    />
  </div>
</template>

<style scoped>
.terminal-shell {
  display: grid;
  grid-template-columns: var(--spacing-filetree) 1fr var(--spacing-right-panel);
  grid-template-rows: 1fr var(--spacing-statusbar);
  grid-template-areas:
    "filetree chat right"
    "statusbar statusbar statusbar";
  height: 100vh;
  overflow: hidden;
}

/* WHY data 属性驱动而非 v-if 动态类：CSS transition 更平滑 */
.terminal-shell[data-filetree-collapsed="true"] {
  grid-template-columns: 0 1fr var(--spacing-right-panel);
}

.panel-left { grid-area: filetree; }
.panel-center { grid-area: chat; }
.panel-right { grid-area: right; }
.panel-bottom { grid-area: statusbar; }

/* 面板折叠 transition */
.panel-left,
.panel-right {
  transition: width 0.15s ease;
}
</style>
