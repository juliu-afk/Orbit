<script setup lang="ts">
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

watch(() => session.currentSessionId, (newId) => { if (newId) chat.connectChatWs(newId, session.currentProjectName || '') })

function onKeydown(e: KeyboardEvent) {
  if ((e.metaKey || e.ctrlKey) && e.key === 'b') { e.preventDefault(); shell.toggleFileTree() }
  if (e.key === 'Escape') { shell.closeAllDrawers(); if (shell.showMonaco) shell.closeFileReview() }
}

onMounted(async () => {
  window.addEventListener('keydown', onKeydown)
  ws.setMessageHandler((msg) => {
    switch (msg.type) {
      case 'task:update': task.handleTaskUpdate(msg.payload as Record<string, unknown>); break
      case 'metrics:snapshot': agentops.handleWsEvent('metrics:snapshot', msg.payload as Record<string, unknown>); break
      case 'agentops:alert': agentops.handleWsEvent('agentops:alert', msg.payload as Record<string, unknown>); break
    }
  })
  ws.connect(`ws://${window.location.host}/ws/dashboard`)
  await session.fetchSessions()
  if (!session.currentSessionId && session.sessions.length > 0) await session.switchToSession(session.sessions[0].session_id)
  if (session.currentSessionId) chat.connectChatWs(session.currentSessionId, session.currentProjectName || '')
  agentops.startPolling()
})

onUnmounted(() => {
  window.removeEventListener('keydown', onKeydown)
  ws.disconnect(); chat.disconnect(); agentops.stopPolling(); task.reset()
})
</script>

<template>
<div class="terminal-shell glass" :data-filetree-collapsed="!shell.showFileTree" @contextmenu.prevent>
  <aside v-show="shell.showFileTree" class="panel-left" style="border-right:1px solid var(--color-orbit-border);overflow-y:auto">
    <!-- P2-7: TODO 接入 FileTreePanel 组件——当前为占位。文件树数据来自 /api/v1/files/tree -->
    <div class="p-3 text-xs" style="color:var(--color-orbit-text-muted);font-family:var(--font-mono)">FILES</div>
  </aside>
  <main class="panel-center flex flex-col overflow-hidden"><TerminalChat /></main>
  <aside class="panel-right" style="border-left:1px solid var(--color-orbit-border);overflow-y:auto">
    <MonacoPanel v-if="shell.showMonaco" />
    <AgentInfoPanel v-else />
  </aside>
  <StatusBar class="panel-bottom" :connection-status="ws.connectionStatus.value" @toggle-dag="shell.toggleDAG()" @toggle-chart="shell.toggleChart()" @toggle-search="shell.toggleSearch()" />
  <DAGDrawer v-model:show="shell.showDAG" />
  <TokenChartDrawer v-model:show="shell.showChart" />
  <SearchDrawer v-model:show="shell.showSearch" @open-file="shell.openFileReview" />
</div>
</template>

<style scoped>
.terminal-shell { display:grid; grid-template-columns:var(--spacing-filetree) 1fr var(--spacing-right-panel); grid-template-rows:1fr var(--spacing-statusbar); grid-template-areas:"filetree chat right" "statusbar statusbar statusbar"; height:100vh; overflow:hidden }
.terminal-shell[data-filetree-collapsed="true"] { grid-template-columns:0 1fr var(--spacing-right-panel) }
.panel-left{grid-area:filetree}.panel-center{grid-area:chat}.panel-right{grid-area:right}.panel-bottom{grid-area:statusbar}
</style>
