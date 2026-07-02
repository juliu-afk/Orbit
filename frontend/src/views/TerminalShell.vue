<script setup lang="ts">
import { onMounted, onUnmounted, watch, ref } from 'vue'
import { useShellStore } from '@/stores/shell'
import { useSessionStore } from '@/stores/session'
import { useAgentOpsStore } from '@/stores/agentops'
import { useChatStore } from '@/stores/chat'
import { useTaskStore } from '@/stores/task'
import { usePeakStore } from '@/stores/peak'
import { useEditorStore } from '@/stores/editor'
import { useWebSocket } from '@/composables/useWebSocket'
import { apiGet } from '@/services/api'
import StatusBar from '@/components/layout/StatusBar.vue'
import TerminalChat from '@/components/chat/TerminalChat.vue'
import MonacoPanel from '@/components/editor/MonacoPanel.vue'
import AgentInfoPanel from '@/components/resources/AgentInfoPanel.vue'
import FileTreePanel from '@/components/editor/FileTreePanel.vue'
import type { FileNode } from '@/components/editor/FileTreePanel.vue'
import DAGDrawer from '@/components/dag/DAGDrawer.vue'
import TokenChartDrawer from '@/components/charts/TokenChartDrawer.vue'
import SearchDrawer from '@/components/editor/SearchDrawer.vue'
import ScheduleDrawer from '@/components/schedule/ScheduleDrawer.vue'
import PeakPromptDialog from '@/components/chat/PeakPromptDialog.vue'
import type { PeakPromptData } from '@/stores/peak'

const shell = useShellStore()
const session = useSessionStore()
const agentops = useAgentOpsStore()
const chat = useChatStore()
const task = useTaskStore()
const editor = useEditorStore()
const ws = useWebSocket()

// 文件树数据
const fileTree = ref<FileNode[]>([])

// WHY 复用旧 ReviewView 的 buildTree 逻辑——扁平路径 → 嵌套 FileNode[]
function buildTree(files: Array<{ path: string }>): FileNode[] {
  const root: FileNode[] = []
  const dirMap = new Map<string, FileNode>()
  for (const f of files) {
    const parts = f.path.split('/').filter(Boolean)
    let parent = root
    let currentPath = ''
    for (let i = 0; i < parts.length; i++) {
      const part = parts[i]
      const isLast = i === parts.length - 1
      currentPath = currentPath ? `${currentPath}/${part}` : part
      if (isLast) {
        parent.push({ name: part, path: f.path, isDir: false })
      } else {
        let dir = dirMap.get(currentPath)
        if (!dir) {
          dir = { name: part, path: currentPath, isDir: true, children: [] }
          dirMap.set(currentPath, dir)
          parent.push(dir)
        }
        parent = dir.children!
      }
    }
  }
  return root
}

async function fetchFileTree() {
  try {
    const data = await apiGet<{ files: Array<{ path: string }> }>('/api/v1/files/tree')
    if (data.files) fileTree.value = buildTree(data.files)
  } catch { /* 后端不可用时空树 */ }
}

// WHY openFile: editor store 拉 diff 内容 + shell 打开 Monaco 面板
async function onSelectFile(path: string) {
  await editor.openFile(path)
  shell.openFileReview(path)
}

watch(() => session.currentSessionId, (newId) => { if (newId) chat.connectChatWs(newId, session.currentProjectName || '') })

function onKeydown(e: KeyboardEvent) {
  if ((e.metaKey || e.ctrlKey) && e.key === 'b') { e.preventDefault(); shell.toggleFileTree() }
  if (e.key === 'Escape') { shell.closeAllDrawers(); if (shell.showMonaco) shell.closeFileReview() }
}

// D13: 高峰避让弹窗
const showPeakPrompt = ref(false)
const peakPromptData = ref<PeakPromptData | null>(null)
watch(() => chat.lastPeakPrompt, (d: PeakPromptData | null) => { if (d) { peakPromptData.value = d; showPeakPrompt.value = true } })
function onPeakDefer() { showPeakPrompt.value = false; chat.resubmitWithDefer() }
function onPeakUrgent() { showPeakPrompt.value = false; chat.resubmitWithUrgent() }

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
  peak.fetchPeakStatus()  // D13: 拉取高峰避让状态
  fetchFileTree()  // v0.22.1: 加载文件树
})

onUnmounted(() => {
  window.removeEventListener('keydown', onKeydown)
  ws.disconnect(); chat.disconnect(); agentops.stopPolling(); task.reset()
})
</script>

<template>
<div class="terminal-shell glass" :data-filetree-collapsed="!shell.showFileTree" @contextmenu.prevent>
  <aside v-show="shell.showFileTree" class="panel-left" style="border-right:1px solid var(--color-orbit-border);overflow-y:auto">
    <FileTreePanel :tree-data="fileTree" :selected-file="shell.selectedFile" @select-file="onSelectFile" />
  </aside>
  <main class="panel-center flex flex-col overflow-hidden"><TerminalChat /></main>
  <aside class="panel-right" style="border-left:1px solid var(--color-orbit-border);overflow-y:auto">
    <MonacoPanel v-if="shell.showMonaco" />
    <AgentInfoPanel v-else />
  </aside>
  <StatusBar class="panel-bottom" :connection-status="ws.connectionStatus.value" @toggle-dag="shell.toggleDAG()" @toggle-chart="shell.toggleChart()" @toggle-search="shell.toggleSearch()" @toggle-schedule="shell.toggleSchedule()" />
  <DAGDrawer v-model:show="shell.showDAG" />
  <TokenChartDrawer v-model:show="shell.showChart" />
  <SearchDrawer v-model:show="shell.showSearch" @open-file="shell.openFileReview" />
  <ScheduleDrawer v-model:visible="shell.showSchedule" />
  <PeakPromptDialog v-model:visible="showPeakPrompt" :data="peakPromptData" @defer="onPeakDefer" @urgent="onPeakUrgent" @cancel="showPeakPrompt = false" />
</div>
</template>

<style scoped>
.terminal-shell { display:grid; grid-template-columns:var(--spacing-filetree) 1fr var(--spacing-right-panel); grid-template-rows:1fr var(--spacing-statusbar); grid-template-areas:"filetree chat right" "statusbar statusbar statusbar"; height:100vh; overflow:hidden }
.terminal-shell[data-filetree-collapsed="true"] { grid-template-columns:0 1fr var(--spacing-right-panel) }
.panel-left{grid-area:filetree}.panel-center{grid-area:chat}.panel-right{grid-area:right}.panel-bottom{grid-area:statusbar}
</style>
