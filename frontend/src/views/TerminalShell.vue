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
import DAGDrawer from '@/components/dag/DAGDrawer.vue'
import TokenChartDrawer from '@/components/charts/TokenChartDrawer.vue'
import SearchDrawer from '@/components/editor/SearchDrawer.vue'
import TraceDrawer from '@/components/observability/TraceDrawer.vue'
import ConfigDrawer from '@/components/config/ConfigDrawer.vue'
import CodeGraphDrawer from '@/components/codegraph/CodeGraphDrawer.vue'
import WechatBindingPanel from '@/components/settings/WechatBindingPanel.vue'
import ShortcutPanel from '@/components/layout/ShortcutPanel.vue'
import CommandPalette from '@/components/layout/CommandPalette.vue'  // UX-11
import NewSessionDialog from '@/components/layout/NewSessionDialog.vue'
import MonacoDiffEditor from '@/components/editor/MonacoDiffEditor.vue'  // UX-2
import RulesPanel from '@/components/settings/RulesPanel.vue'  // UX-10
import BranchesPanel from '@/components/session/BranchesPanel.vue'  // UX-13

const shell = useShellStore(); const session = useSessionStore(); const agentops = useAgentOpsStore()
const chat = useChatStore(); const task = useTaskStore(); const editor = useEditorStore()
const settings = useSettingsStore(); const ws = useWebSocket()
const fileTree = ref<FileNode[]>([]); const showShortcuts = ref(false); const showNewDialog = ref(false); const showCodeDiff = ref(false)
const showCommandPalette = ref(false); const showRules = ref(false)  // UX-11, UX-10

function buildTree(files: Array<{ path: string }>): FileNode[] {
  const root: FileNode[] = []; const dirMap = new Map<string, FileNode>()
  for (const f of files) { const parts = f.path.split("/").filter(Boolean); let parent = root; let cp = ""
    for (let i=0; i<parts.length; i++) { const p=parts[i]; cp=cp?`${cp}/${p}`:p
      if (i===parts.length-1) parent.push({name:p,path:f.path,isDir:false})
      else { let d=dirMap.get(cp); if(!d){d={name:p,path:cp,isDir:true,children:[]};dirMap.set(cp,d);parent.push(d)}; parent=d.children! } } }
  return root
}
async function fetchFileTree(){ try{ const dir=session.currentProjectPath; const url=dir?`/api/v1/files/tree?dir=${encodeURIComponent(dir)}`:"/api/v1/files/tree"; const d=await apiGet<{files:Array<{path:string}>}>(url); if(d.files)fileTree.value=buildTree(d.files) }catch{} }
async function onSelectFile(path:string){ await editor.openFile(path); shell.openFileReview(path) }

// WHY: 项目文件夹选择后重建上下文——刷新 session/chat/文件树
async function onSessionCreated() {
  if (session.messages.length > 0) {
    chat.restoreMessages(session.messages.map(m => ({
      role: m.role, content: m.content, created_at: m.created_at,
    })))
  }
  agentops.fetchAll()
  fetchFileTree()
  if (session.currentSessionId) {
    chat.connectChatWs(session.currentSessionId, session.currentProjectName)
  }
}

// WHY: session 切换后刷新上下文——和 onSessionCreated 同逻辑，但不需要 restoreMessages（已在 switchToSession 中加载）
function onSessionSwitched(_sessionId: string) {
  chat.reset()
  agentops.fetchAll()
  fetchFileTree()
  if (session.currentSessionId) {
    chat.connectChatWs(session.currentSessionId, session.currentProjectName)
  }
}

// WHY: 代码产物就绪 → 自动弹出抽屉——从 DashboardView 移植到 TerminalShell
watch(() => task.hasCodeOutput, (show) => {
  if (show) showCodeDiff.value = true
})

function handleCloseCodeDiff() {
  showCodeDiff.value = false
  task.consumeCodeOutput()
}

function gridAreas():string{ const cols=settings.fileTreeLeft?"filetree chat right":"chat right filetree"; return `"${cols}" "statusbar statusbar statusbar"` }
// WHY 行内样式计算: CSS 选择器覆盖不了 inline style，必须在这里响应折叠状态
const gridColumns = () => shell.showFileTree
  ? `var(--spacing-filetree) 1fr var(--spacing-right-panel)`
  : `0 1fr var(--spacing-right-panel)`

watch(()=>session.currentSessionId,(n)=>{if(n)chat.connectChatWs(n,session.currentProjectName||"")})
function onKeydown(e:KeyboardEvent){ if((e.metaKey||e.ctrlKey)&&e.key==='b'){e.preventDefault();shell.toggleFileTree()}; if((e.metaKey||e.ctrlKey)&&e.shiftKey&&e.key==='B'){e.preventDefault();shell.showBranches=!shell.showBranches}; if((e.metaKey||e.ctrlKey)&&e.key==='/'){e.preventDefault();showShortcuts.value=!showShortcuts.value}; if((e.metaKey||e.ctrlKey)&&e.key==='k'){e.preventDefault();showCommandPalette.value=!showCommandPalette.value}; if(e.key==='Escape'){shell.closeAllDrawers();if(shell.showMonaco)shell.closeFileReview()} }
// UX-11: 命令面板操作分发
function onCmdExecute(action: string) {
  switch (action) {
    case 'toggle:filetree': shell.toggleFileTree(); break
    case 'toggle:search': shell.showSearch = !shell.showSearch; break
    case 'toggle:dag': shell.showDAG = !shell.showDAG; break
    case 'toggle:charts': shell.showChart = !shell.showChart; break
    case 'toggle:trace': shell.showTrace = !shell.showTrace; break
    case 'toggle:config': shell.showConfig = !shell.showConfig; break
    case 'open:settings': showShortcuts.value = true; break
    case 'open:newsession': showNewDialog.value = true; break
    case 'open:shortcuts': showShortcuts.value = true; break
    case 'open:rules': showRules.value = true; break
    case 'toggle:branches': shell.showBranches = !shell.showBranches; break
  }
}

function startResize(edge:"left"|"right",e:PointerEvent){ e.preventDefault();(e.target as HTMLElement).setPointerCapture(e.pointerId); const onMove=(ev:PointerEvent)=>{ if(edge==="left")settings.fileTreeWidth=Math.max(160,Math.min(480,ev.clientX)); else settings.rightPanelWidth=Math.max(180,Math.min(600,window.innerWidth-ev.clientX)) }; window.addEventListener("pointermove",onMove); const clean=()=>window.removeEventListener("pointermove",onMove); window.addEventListener("pointerup",clean,{once:true}); window.addEventListener("pointercancel",clean,{once:true}) }
// P2 fix: 具名函数引用避免每次渲染创建新闭包
const handleLeftResize = (e: PointerEvent) => startResize('left', e)
const handleRightResize = (e: PointerEvent) => startResize('right', e)

onMounted(async()=>{ window.addEventListener("keydown",onKeydown); ws.setMessageHandler((msg)=>{switch(msg.type){case"task:update":task.handleTaskUpdate(msg.payload as Record<string,unknown>);break;case"metrics:snapshot":agentops.handleWsEvent("metrics:snapshot",msg.payload as Record<string,unknown>);break;case"agentops:alert":agentops.handleWsEvent("agentops:alert",msg.payload as Record<string,unknown>);break}}); ws.connect("ws://"+window.location.host+"/ws/dashboard"); await session.fetchSessions(); if(!session.currentSessionId&&session.sessions.length>0)await session.switchToSession(session.sessions[0].session_id); if(session.currentSessionId)chat.connectChatWs(session.currentSessionId,session.currentProjectName||""); agentops.startPolling(); fetchFileTree() })
onUnmounted(()=>{ window.removeEventListener("keydown",onKeydown); ws.disconnect(); chat.disconnect(); agentops.stopPolling(); task.reset() })
</script>

<template>
<div class="terminal-shell glass" :data-filetree-collapsed="!shell.showFileTree" :style="{gridTemplateAreas:gridAreas(),gridTemplateColumns:gridColumns()}" @contextmenu.prevent>
  <div v-show="shell.showFileTree" class="resize-handle resize-left" @pointerdown="handleLeftResize" />
  <aside v-show="shell.showFileTree" class="panel-left" style="border-right:1px solid var(--color-orbit-border);overflow-y:auto"><FileTreePanel :tree-data="fileTree" :selected-file="shell.selectedFile" @select-file="onSelectFile" /></aside>
  <main class="panel-center flex flex-col overflow-hidden">
        <!-- 无 Session 引导——为什么没有自动创建：用户需主动选择项目文件夹 -->
        <div v-if="!session.currentSessionId" class="welcome-empty">
          <div class="welcome-icon">🪐</div>
          <h2 class="welcome-title">Welcome to Orbit</h2>
          <p class="welcome-desc">Select a project folder to get started</p>
          <button class="open-btn" @click="showNewDialog = true">Open or Create Project</button>
        </div>
        <TerminalChat v-else />
      </main>
  <div class="resize-handle resize-right" @pointerdown="handleRightResize" />
  <aside class="panel-right" style="border-left:1px solid var(--color-orbit-border);overflow-y:auto"><MonacoPanel v-if="shell.showMonaco" /><AgentInfoPanel v-else /></aside>
  <StatusBar class="panel-bottom" :connection-status="ws.connectionStatus.value" @toggle-dag="shell.toggleDAG()" @toggle-chart="shell.toggleChart()" @toggle-search="shell.toggleSearch()" @toggle-trace="shell.toggleTrace()" @toggle-config="shell.toggleConfig()" @toggle-codegraph="shell.toggleCodeGraph()" @toggle-wechat="shell.toggleWeChat()" @toggle-branches="shell.showBranches = !shell.showBranches" @new-session="showNewDialog = true" @switch-session="onSessionSwitched" />
  <DAGDrawer v-model:show="shell.showDAG" /><TokenChartDrawer v-model:show="shell.showChart" /><SearchDrawer v-model:show="shell.showSearch" @open-file="shell.openFileReview" />
  <TraceDrawer v-model:show="shell.showTrace" /><ConfigDrawer v-model:show="shell.showConfig" />
  <CodeGraphDrawer v-model:show="shell.showCodeGraph" />
  <WechatBindingPanel v-model:show="shell.showWeChat" />
  <ShortcutPanel v-model:show="showShortcuts" />
    <!-- UX-11: 命令面板 Cmd+K -->
    <CommandPalette :visible="showCommandPalette" @close="showCommandPalette = false" @execute="onCmdExecute" />
    <!-- UX-10: Rules 面板 -->
    <el-drawer v-model="showRules" title="Rules & Memory" direction="rtl" size="480px"><RulesPanel /></el-drawer>
    <!-- UX-13: 对话分支 -->
    <el-drawer v-model="shell.showBranches" title="Conversation Branches" direction="rtl" size="360px"><BranchesPanel /></el-drawer>
  <NewSessionDialog v-model:visible="showNewDialog" @confirmed="onSessionCreated" />
  <!-- WHY 代码产物抽屉: task:update WS 推送代码 output → 自动弹出展示 -->
  <el-drawer v-model="showCodeDiff" title="Generated Code" direction="rtl" size="520px" @close="handleCloseCodeDiff">
    <MonacoDiffEditor v-if="task.codeOutput" original="" :modified="task.codeOutput" language="python" height="calc(100vh - 80px)" />
  </el-drawer>
</div>
</template>

<style scoped>
.terminal-shell { display:grid; grid-template-columns:var(--spacing-filetree) 1fr var(--spacing-right-panel); grid-template-rows:1fr var(--spacing-statusbar); grid-template-areas:v-bind(gridAreas()); height:100%; overflow:hidden }
.terminal-shell[data-filetree-collapsed="true"] { grid-template-columns:0 1fr var(--spacing-right-panel) }
.panel-left{grid-area:filetree;background:var(--color-orbit-glass);backdrop-filter:blur(var(--glass-blur,12px))}.panel-center{grid-area:chat}.panel-right{grid-area:right;background:var(--color-orbit-glass);backdrop-filter:blur(var(--glass-blur,12px))}.panel-bottom{grid-area:statusbar}
.resize-handle{width:4px;cursor:col-resize;background:transparent;transition:background 0.15s;z-index:10}
.resize-handle:hover,.resize-handle:active{background:var(--color-orbit-accent)}
.resize-left{grid-area:filetree;justify-self:end}
.resize-right{grid-area:right;justify-self:start}
/* 无 Session 引导 */
.welcome-empty { flex: 1; display: flex; flex-direction: column; justify-content: center; align-items: center; gap: 12px; color: var(--color-orbit-text-secondary); font-family: var(--font-mono); }
.welcome-icon { font-size: 48px; margin-bottom: 8px; }
.welcome-title { font-size: 20px; font-weight: 600; color: var(--color-orbit-text); margin: 0; }
.welcome-desc { font-size: 13px; color: var(--color-orbit-text-muted); margin: 0 0 16px; }
.open-btn { padding: 10px 24px; background: var(--color-orbit-accent); border: none; border-radius: 6px; color: #fff; font-size: 14px; font-family: var(--font-mono); cursor: pointer; transition: opacity 0.15s; }
.open-btn:hover { opacity: 0.85; }
</style>
