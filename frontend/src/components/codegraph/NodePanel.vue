<!-- 节点详情面板——点击节点后展示文件信息 + 符号列表。 -->
<script setup lang="ts">
import { computed } from 'vue'
import { useCodeGraphStore } from '@/stores/codegraph'

const store = useCodeGraphStore()

const selectedNode = computed(() => {
  if (!store.selectedNodeId) return null
  return store.elements.find(e => e.data.id === store.selectedNodeId)
})

const nodeData = computed(() => selectedNode.value?.data)

// 找到与该节点相连的边
const relatedEdges = computed(() => {
  if (!store.selectedNodeId) return []
  return store.edges.filter(e =>
    e.data.source === store.selectedNodeId || e.data.target === store.selectedNodeId
  )
})

const inDegree = computed(() =>
  relatedEdges.value.filter(e => e.data.target === store.selectedNodeId).length
)
const outDegree = computed(() =>
  relatedEdges.value.filter(e => e.data.source === store.selectedNodeId).length
)
</script>

<template>
  <div v-if="selectedNode" class="node-panel">
    <h3 class="panel-title">{{ nodeData?.label || nodeData?.name || '未命名节点' }}</h3>

    <div class="panel-section">
      <div class="field">
        <span class="field-label">类型</span>
        <span class="field-value tag">{{ nodeData?.type }}</span>
      </div>
      <div v-if="nodeData?.file_path" class="field">
        <span class="field-label">路径</span>
        <code class="field-value path">{{ nodeData?.file_path }}</code>
      </div>
      <div class="stats-row">
        <div class="stat">
          <span class="stat-value">{{ nodeData?.symbol_count ?? '-' }}</span>
          <span class="stat-label">符号</span>
        </div>
        <div class="stat">
          <span class="stat-value">{{ inDegree }}</span>
          <span class="stat-label">入度</span>
        </div>
        <div class="stat">
          <span class="stat-value">{{ outDegree }}</span>
          <span class="stat-label">出度</span>
        </div>
      </div>
    </div>

    <div class="panel-actions">
      <button class="action-btn" @click="store.selectNode(null)" title="取消选中">
        取消选中
      </button>
    </div>
  </div>

  <div v-else class="node-panel empty">
    <p class="empty-text">点击节点查看详情</p>
    <p class="empty-hint">或搜索框输入文件名/符号名定位</p>
  </div>
</template>

<style scoped>
.node-panel {
  padding: 16px; font-family: var(--font-mono);
  color: var(--color-orbit-text); font-size: 13px;
  height: 100%; overflow-y: auto;
}
.node-panel.empty { display: flex; flex-direction: column; align-items: center; justify-content: center; }
.panel-title { font-size: 15px; font-weight: 600; margin: 0 0 16px; color: #e0e0e0; word-break: break-all; }
.panel-section { margin-bottom: 16px; }
.field { margin-bottom: 10px; }
.field-label { display: block; color: var(--color-orbit-text-muted); font-size: 11px; margin-bottom: 2px; }
.field-value { word-break: break-all; }
.tag { background: rgba(99,102,241,.2); color: #818cf8; padding: 2px 8px; border-radius: 4px; font-size: 12px; }
.path { font-size: 12px; color: #94a3b8; }
.stats-row { display: flex; gap: 16px; margin-top: 12px; }
.stat { text-align: center; }
.stat-value { display: block; font-size: 18px; font-weight: 600; color: #e0e0e0; }
.stat-label { font-size: 11px; color: var(--color-orbit-text-muted); }
.panel-actions { margin-top: 16px; }
.action-btn {
  width: 100%; background: rgba(255,255,255,.06); border: 1px solid var(--color-orbit-border);
  border-radius: 4px; color: var(--color-orbit-text); padding: 6px 12px;
  font-family: inherit; font-size: 12px; cursor: pointer;
}
.action-btn:hover { background: rgba(255,255,255,.1); }
.empty-text { font-size: 14px; color: var(--color-orbit-text-muted); margin: 0; }
.empty-hint { font-size: 12px; color: var(--color-orbit-text-muted); margin: 8px 0 0; opacity: 0.6; }
</style>
