<script setup lang="ts">
import { onMounted, onUnmounted, watch, ref } from 'vue'
import { useShellStore } from '@/stores/shell'
import { useSessionStore } from '@/stores/session'
import { useAgentOpsStore } from '@/stores/agentops'
import { useChatStore } from '@/stores/chat'
import { useTaskStore } from '@/stores/task'
import { useEditorStore } from '@/stores/editor'
import { useSettingsStore } from '@/stores/settings'
import { useWebSocket } from '@/composables/useWebSocket'
import { apiGet } from '@/services/api'
import StatusBar from '@/components/layout/StatusBar.vue'
import TerminalChat from '@/components/chat/TerminalChat.vue'
import MonacoPanel from '@/components/editor/MonacoPanel.vue'
import AgentInfoPanel from '@/components/resources/AgentInfoPanel.vue'
import FileTreePanel from '@/components/editor/FileTreePanel.vue'
import type { FileNode } from '@/components/editor/FileTreePanel.vue'
import SettingsDialog from '@/components/layout/SettingsDialog.vue'
import DAGDrawer from '@/components/dag/DAGDrawer.vue'
import TokenChartDrawer from '@/components/charts/TokenChartDrawer.vue'
import SearchDrawer from '@/components/editor/SearchDrawer.vue'

const shell = useShellStore(); const session = useSessionStore(); const agentops = useAgentOpsStore()
const chat = useChatStore(); const task = useTaskStore(); const editor = useEditorStore()
const settings = useSettingsStore(); const ws = useWebSocket()

const fileTree = ref<FileNode[]>([]); const showSettings = ref(false)

function buildTree(files: Array<{ path: string }>): FileNode[] {
  const root: FileNode[] = []; const dirMap = new Map<string, FileNode>()
  for (const f of files) { const parts = f.path.split('/').filter(Boolean); let parent = root; let cp = ''
    for (let i = 0; i < parts.length; i++) { const part = parts[i]; cp = cp ? `${cp}/${part}` : part
      if (i === parts.length - 1) parent.push({ name: part, path: f.path, isDir: false })
      else { let d = dirMap.get(cp); if (!d) { d = { name: part, path: cp, isDir: true, children: [] }; dirMap.set(cp, d); parent.push(d) }; parent = d.children! } } }
  return root
}
async function fetchFileTree() { try { const d = await apiGet<{ files: Array<{ path: string }> }>('/api/v1/files/tree'); if (d.files) fileTree.value = buildTree(d.files) } catch { /* offline */ } }
async function onSelectFile(path: string) { await editor.openFile(path); shell.openFileReview(path) }

function gridAreas(): string { const cols = settings.fileTreeLeft ? 'filetree chat right' : 'chat right filetree'; return `"${cols}" "statusbar statusbar statusbar"` }

watch(() => session.currentSessionId, (n) => { if (n) chat.connectChatWs(n, session.currentProjectName || '') })

function onKeydown(e: KeyboardEvent) { if ((e.metaKey || e.ctrlKey) && e.key === 'b') { e.preventDefault(); shell.toggleFileTree() }; if (e.key === 'Escape') { shell.closeAllDrawers(); if (shell.showMonaco) shell.closeFileReview() } }

function startResize(edge: 'left' | 'right', e: PointerEvent) { e.preventDefault(); (e.target as HTMLElement).setPointerCapture(e.pointerId); const onMove = (ev: PointerEvent) => { if (edge === 'left') settings.fileTreeWidth = Math.max(160, Math.min(480, ev.clientX)); else settings.rightPanelWidth = Math.max(180, Math.min(600, window.innerWidth - ev.clientX)) }; window.addEventListener('pointermove', onMove); const clean = () => window.removeEventListener('pointermove', onMove); window.addEventListener('pointerup', clean, { once: true }); window.addEventListener('pointercancel', clean, { once: true }) }

onMounted(async () => { window.addEventListener('keydown', onKeydown); ws.setMessageHandler((msg) => { switch (msg.type) { case 'task:update': task.handleTaskUpdate(msg.payload as Record<string, unknown>); break; case 'metrics:snapshot': agentops.handleWsEvent('metrics:snapshot', msg.payload as Record<string, unknown>); break; case 'agentops:alert': agentops.handleWsEvent('agentops:alert', msg.payload as Record<string, unknown>); break } }); ws.connect(`ws://${window.location.host}/ws/dashboard`); await session.fetchSessions(); if (!session.currentSessionId && session.sessions.length > 0) await session.switchToSession(session.sessions[0].session_id); if (session.currentSessionId) chat.connectChatWs(session.currentSessionId, session.currentProjectName || ''); agentops.startPolling(); fetchFileTree() })
onUnmounted(() => { window.removeEventListener('keydown', onKeydown); ws.disconnect(); chat.disconnect(); agentops.stopPolling(); task.reset() })
</script>

<template>
<div class="terminal-shell glass" :data-filetree-collapsed="!shell.showFileTree" :style="{ gridTemplateAreas: gridAreas() }" @contextmenu.prevent>
  <div v-show="shell.showFileTree" class="resize-handle resize-left" @pointerdown="(e) => startResize('left', e)" />
  <aside v-show="shell.showFileTree" class="panel-left" style="border-right:1px solid var(--color-orbit-border);overflow-y:auto"><FileTreePanel :tree-data="fileTree" :selected-file="shell.selectedFile" @select-file="onSelectFile" /></aside>
  <main class="panel-center flex flex-col overflow-hidden"><TerminalChat /></main>
  <div class="resize-handle resize-right" @pointerdown="(e) => startResize('right', e)" />
  <aside class="panel-right" style="border-left:1px solid var(--color-orbit-border);overflow-y:auto"><MonacoPanel v-if="shell.showMonaco" /><AgentInfoPanel v-else /></aside>
  <StatusBar class="panel-bottom" :connection-status="ws.connectionStatus.value" @toggle-dag="shell.toggleDAG()" @toggle-chart="shell.toggleChart()" @toggle-search="shell.toggleSearch()" @open-settings="showSettings = true" />
  <DAGDrawer v-model:show="shell.showDAG" /><TokenChartDrawer v-model:show="shell.showChart" /><SearchDrawer v-model:show="shell.showSearch" @open-file="shell.openFileReview" />
  <SettingsDialog v-model:show="showSettings" />
</div>
</template>

<style scoped>
.terminal-shell { display:grid; grid-template-columns:var(--spacing-filetree) 1fr var(--spacing-right-panel); grid-template-rows:1fr var(--spacing-statusbar); grid-template-areas:v-bind(gridAreas()); height:100vh; overflow:hidden }
.terminal-shell[data-filetree-collapsed="true"] { grid-template-columns:0 1fr var(--spacing-right-panel) }
.panel-left{grid-area:filetree}.panel-center{grid-area:chat}.panel-right{grid-area:right}.panel-bottom{grid-area:statusbar}
.resize-handle{width:4px;cursor:col-resize;background:transparent;transition:background 0.15s;z-index:10}
.resize-handle:hover,.resize-handle:active{background:var(--color-orbit-accent)}
.resize-left{grid-area:filetree;justify-self:end}
.resize-right{grid-area:right;justify-self:start}
</style>
