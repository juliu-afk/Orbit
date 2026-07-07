<!-- MCP 服务器管理页面 -->
<template>
<div class="mcp-page">
  <!-- 页头 -->
  <div class="mcp-topbar" data-tauri-drag-region>
    <el-button text class="back-btn" @click="goBack">
      ← 返回
    </el-button>
    <h2 class="mcp-title">MCP 服务器</h2>
    <span class="mcp-subtitle">管理外部 MCP 服务器连接与工具</span>
    <div class="mcp-topbar-actions">
      <el-button size="small" :loading="store.loading" @click="store.fetchServers()">刷新</el-button>
    </div>
  </div>

  <!-- 错误提示 -->
  <div v-if="store.error" class="mcp-error">
    <el-alert :title="store.error" type="error" show-icon :closable="false" />
  </div>

  <!-- 加载态 -->
  <div v-if="store.loading && store.servers.length === 0" class="mcp-loading">
    <el-skeleton :rows="3" animated />
  </div>

  <!-- 空态 -->
  <div v-else-if="store.servers.length === 0" class="mcp-empty">
    <el-empty description="暂无 MCP 服务器配置" />
  </div>

  <!-- 服务器列表 -->
  <div v-else class="mcp-server-list">
    <el-card
      v-for="s in store.servers"
      :key="s.name"
      class="mcp-server-card"
      shadow="never"
    >
      <div class="server-row" @click="handleToggleExpand(s.name)">
        <!-- 状态点 -->
        <span class="server-dot" :class="`dot--${s.status}`" />

        <!-- 服务器基本信息 -->
        <div class="server-info">
          <span class="server-name">{{ s.name }}</span>
          <span class="server-command">{{ s.command }} {{ s.args?.join(' ') }}</span>
        </div>

        <!-- 状态文本 -->
        <span class="server-status-label">{{ statusLabel(s.status) }}</span>

        <!-- 工具计数 -->
        <el-tag size="small" :type="s.tools_count > 0 ? 'success' : 'info'" class="tool-count">
          {{ s.tools_count ?? 0 }} 工具
        </el-tag>

        <!-- 启用开关 -->
        <el-switch
          :model-value="s.enabled"
          size="small"
          @click.stop
          @change="(v: boolean) => store.toggleServer(s.name, v)"
        />

        <!-- 展开箭头 -->
        <span class="expand-arrow" :class="{ expanded: expandedServer === s.name }">▸</span>
      </div>

      <!-- 展开的工具列表 -->
      <div v-if="expandedServer === s.name" class="server-tools-panel">
        <McpToolList :server-name="s.name" />
      </div>
    </el-card>
  </div>
</div>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { useMcpStore } from '@/stores/mcp'
import type { McpServer } from '@/stores/mcp'
import McpToolList from '@/components/mcp/McpToolList.vue'

const router = useRouter()
const store = useMcpStore()
const expandedServer = ref<string | null>(null)

onMounted(() => {
  store.fetchServers()
})

function goBack() {
  router.push('/app')
}

function statusLabel(status: McpServer['status']): string {
  switch (status) {
    case 'connected': return '已连接'
    case 'disabled': return '已禁用'
    case 'error': return '异常'
    default: return '未知'
  }
}

function handleToggleExpand(name: string) {
  expandedServer.value = expandedServer.value === name ? null : name
}
</script>

<style scoped>
.mcp-page {
  height: 100vh;
  overflow: hidden;
  display: flex;
  flex-direction: column;
  background: #0a0a14;
  color: #e0e0e0;
  font-family: var(--font-mono, 'Cascadia Code', 'JetBrains Mono', monospace);
}

/* ── 页头 ── */
.mcp-topbar {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px 16px;
  background: #12122a;
  border-bottom: 1px solid #2a2a4a;
  flex-shrink: 0;
}
.back-btn { color: var(--color-orbit-accent, #7c6ff0); font-size: 12px; }
.mcp-title { font-size: 15px; font-weight: 700; margin: 0; color: #e0e0e0; }
.mcp-subtitle { font-size: 11px; color: #666; flex: 1; }
.mcp-topbar-actions { display: flex; gap: 6px; }

/* ── 错误 ── */
.mcp-error { padding: 8px 16px 0; flex-shrink: 0; }

/* ── 加载 ── */
.mcp-loading { padding: 32px 16px; }

/* ── 空态 ── */
.mcp-empty { display: flex; justify-content: center; align-items: center; min-height: 50vh; }

/* ── 服务器列表 ── */
.mcp-server-list {
  flex: 1;
  overflow-y: auto;
  padding: 12px 16px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.mcp-server-card {
  background: #12122a;
  border: 1px solid #2a2a4a;
  border-radius: 6px;
  cursor: pointer;
}
.mcp-server-card:hover { border-color: #3a3a6a; }

.server-row {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 12px;
}

/* 状态点 */
.server-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  flex-shrink: 0;
}
.dot--connected { background: #4caf50; box-shadow: 0 0 6px rgba(76,175,80,.5); }
.dot--disabled { background: #555; }
.dot--error { background: #f44336; box-shadow: 0 0 6px rgba(244,67,54,.5); }

.server-info { flex: 1; min-width: 0; }
.server-name { font-size: 13px; font-weight: 600; color: #e0e0e0; }
.server-command { display: block; font-size: 10px; color: #666; margin-top: 1px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }

.server-status-label { font-size: 11px; color: #888; }
.tool-count { flex-shrink: 0; }

.expand-arrow {
  font-size: 12px;
  color: #666;
  transition: transform .15s;
  flex-shrink: 0;
}
.expand-arrow.expanded { transform: rotate(90deg); }

/* 展开面板 */
.server-tools-panel {
  padding: 0 12px 12px;
}

/* Element Plus 暗色覆盖 */
:deep(.el-card__body) { padding: 0; }
:deep(.el-switch) { --el-switch-on-color: #4caf50; --el-switch-off-color: #444; }
:deep(.el-tag--success) { background: rgba(76,175,80,.15); border-color: rgba(76,175,80,.3); color: #4caf50; }
:deep(.el-tag--info) { background: rgba(255,255,255,.06); border-color: rgba(255,255,255,.1); color: #999; }
:deep(.el-alert--error) { background: rgba(244,67,54,.1); border: 1px solid rgba(244,67,54,.3); }
:deep(.el-alert__title) { color: #f44336; font-size: 12px; }
</style>
