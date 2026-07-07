<script setup lang="ts">
import { computed } from 'vue'
import { useRouter } from 'vue-router'
import { useShellStore } from '@/stores/shell'
import { useSessionStore } from '@/stores/session'
import type { ConnectionStatus } from '@/composables/useWebSocket'

const props = defineProps<{ connectionStatus: ConnectionStatus }>()
const emit = defineEmits<{
  (e: 'toggle-dag'): void; (e: 'toggle-chart'): void
  (e: 'toggle-search'): void
  (e: 'toggle-trace'): void; (e: 'toggle-config'): void
  (e: 'toggle-codegraph'): void; (e: 'toggle-wechat'): void; (e: 'toggle-branches'): void
  (e: 'new-session'): void
  (e: 'switch-session', sessionId: string): void
}>()
const shell = useShellStore()
const session = useSessionStore()
const router = useRouter()

function goMcp() { router.push('/mcp') }

const connectionLabel = computed(() => {
  switch (props.connectionStatus) {
    case 'connected': return 'orbit'
    case 'connecting': return 'connecting...'
    default: return 'disconnected'
  }
})

// WHY: session 切换后刷新会话上下文——不需要 reload
function handleSwitch(sessionId: string) {
  session.switchToSession(sessionId)
  emit('switch-session', sessionId)
}
</script>

<template>
<div class="status-bar flex items-center justify-between px-3 select-none" style="height:28px;border-top:1px solid var(--color-orbit-border);background:rgba(10,10,20,0.92);font-family:var(--font-mono);font-size:11px;color:var(--color-orbit-text-secondary)">
  <!-- 左侧：工具面板切换 -->
  <div class="flex items-center gap-3">
    <button class="status-btn" :class="{ active: shell.showFileTree }" @click="shell.toggleFileTree()" title="Toggle file tree (Ctrl+B)">Files</button>
    <button class="status-btn" :class="{ active: shell.showDAG }" @click="emit('toggle-dag')">DAG</button>
    <button class="status-btn" :class="{ active: shell.showChart }" @click="emit('toggle-chart')">Charts</button>
    <button class="status-btn" :class="{ active: shell.showSearch }" @click="emit('toggle-search')">Search</button>
    <button class="status-btn" :class="{ active: shell.showTrace }" @click="emit('toggle-trace')">Trace</button>
    <button class="status-btn" :class="{ active: shell.showConfig }" @click="emit('toggle-config')">Config</button>
    <span class="status-sep">|</span>
    <button class="status-btn" :class="{ active: shell.showCodeGraph }" @click="emit('toggle-codegraph')" title="代码依赖图谱">Graph</button>
    <button class="status-btn" :class="{ active: $route?.name === 'mcp' }" @click="goMcp" title="MCP 服务器管理">MCP</button>
    <button class="status-btn" :class="{ active: shell.showWeChat }" @click="emit('toggle-wechat')" title="微信连接">WeChat</button>
    <span class="status-sep">|</span>
    <button class="status-btn" :class="{ active: shell.showBranches }" @click="emit('toggle-branches')" title="对话分支 (Ctrl+Shift+B)">Branches</button>
  </div>

  <!-- 居中：文件名 or 就绪 -->
  <div class="flex items-center gap-2">
    <span v-if="shell.selectedFile">{{ shell.selectedFile }}</span>
    <span v-else style="color:var(--color-orbit-text-muted)">ready</span>
  </div>

  <!-- 右侧：项目选择 + 连接状态 -->
  <div class="flex items-center gap-3">
    <!-- Session 下拉——切换已有项目 -->
    <el-dropdown
      v-if="session.sessions.length > 0"
      @command="handleSwitch"
      trigger="click"
      size="small"
    >
      <span class="session-trigger">
        {{ session.currentProjectName || '选择项目' }}
        <span class="trigger-arrow">▾</span>
      </span>
      <template #dropdown>
        <el-dropdown-menu>
          <el-dropdown-item
            v-for="s in session.sessions"
            :key="s.session_id"
            :command="s.session_id"
            :class="{ 'is-active': s.session_id === session.currentSessionId }"
          >
            <span class="dd-project-name">📁 {{ s.project_name }}</span>
            <span v-if="s.local_path" class="dd-project-path">{{ s.local_path }}</span>
          </el-dropdown-item>
        </el-dropdown-menu>
      </template>
    </el-dropdown>
    <!-- 空状态：提示无项目 -->
    <span v-else class="no-project">No project</span>

    <!-- 新建/打开项目按钮——常驻 -->
    <button class="status-btn new-project-btn" @click="emit('new-session')" title="Open or create project">+ 项目</button>

    <span class="status-sep">|</span>

    <span class="flex items-center gap-1">
      <span class="status-dot" :class="props.connectionStatus"/>{{ connectionLabel }}
    </span>
  </div>
</div>
</template>

<style scoped>
.status-btn { background:none;border:none;color:var(--color-orbit-text-secondary);cursor:pointer;font-family:var(--font-mono);font-size:11px;padding:2px 6px;border-radius:3px;display:flex;align-items:center;gap:4px }
.status-btn:hover { background:rgba(255,255,255,.06) }
.status-btn.active { background:rgba(255,255,255,.1);color:#e0e0e0 }
.new-project-btn { color: var(--color-orbit-accent); font-weight: 500 }

/* Session 下拉 */
.session-trigger { color: var(--color-orbit-accent); cursor: pointer; font-size: 11px; display: flex; align-items: center; gap: 2px; max-width: 140px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap }
.session-trigger:hover { color: #fff }
.trigger-arrow { font-size: 8px; color: var(--color-orbit-text-muted) }
.dd-project-name { font-size: 12px; color: #e0e0e0 }
.dd-project-path { display: block; font-size: 10px; color: #666; margin-top: 1px }
.is-active .dd-project-name { color: var(--color-orbit-accent) }

.no-project { font-size: 11px; color: var(--color-orbit-text-muted) }
.status-sep { color: var(--color-orbit-border); font-size: 11px }
</style>
