<!-- 代码图谱大尺寸抽屉——85% 宽度，三区布局（工具栏 | 画布 | 详情面板）。
     WHY 85% 而非 600px：代码图谱需要大面积画布，DAG 的 600px 太窄。 -->
<script setup lang="ts">
import { watch } from 'vue'
import { useSessionStore } from '@/stores/session'
import { useCodeGraphStore } from '@/stores/codegraph'
import CytoscapeCanvas from './CytoscapeCanvas.vue'
import SearchBar from './SearchBar.vue'
import LayoutSelector from './LayoutSelector.vue'
import NodePanel from './NodePanel.vue'

const props = defineProps<{ show: boolean }>()
const emit = defineEmits<{ (e: 'update:show', v: boolean): void }>()

const session = useSessionStore()
const store = useCodeGraphStore()

// 打开抽屉时加载数据
watch(() => props.show, async (visible) => {
  if (visible && session.currentProjectName) {
    await store.fetchGraphData(session.currentProjectName)
  }
})

function onClose(): void {
  store.reset()
  emit('update:show', false)
}
</script>

<template>
  <el-drawer
    :model-value="props.show"
    title="代码图谱"
    direction="rtl"
    size="85%"
    @update:model-value="onClose"
  >
    <div class="codegraph-layout">
      <!-- 工具栏 -->
      <div class="toolbar">
        <SearchBar />
        <div class="toolbar-right">
          <LayoutSelector />
          <span v-if="store.stats.node_count" class="stats-badge">
            {{ store.stats.node_count }} 节点 / {{ store.stats.edge_count }} 边
          </span>
        </div>
      </div>

      <!-- 主区域 -->
      <div class="main-area">
        <!-- 加载中 -->
        <div v-if="store.loading" class="state-overlay">
          <div class="spinner" />
          <span>正在加载代码图谱…</span>
        </div>

        <!-- 空数据 -->
        <div v-else-if="!store.loading && store.stats.node_count === 0 && !store.error" class="state-overlay">
          <div class="empty-icon">📊</div>
          <h3>尚未构建代码索引</h3>
          <p>该项目无 Python 文件，或代码图谱尚未解析</p>
        </div>

        <!-- 错误 -->
        <div v-else-if="store.error" class="state-overlay">
          <div class="empty-icon">⚠️</div>
          <h3>加载失败</h3>
          <p>{{ store.error }}</p>
          <button class="retry-btn" @click="store.fetchGraphData(session.currentProjectName || '')">重试</button>
        </div>

        <!-- 正常渲染——三区布局 -->
        <template v-else>
          <div class="canvas-area">
            <CytoscapeCanvas />
          </div>
          <div class="detail-area">
            <NodePanel />
          </div>
        </template>
      </div>
    </div>
  </el-drawer>
</template>

<style scoped>
.codegraph-layout {
  display: flex; flex-direction: column; height: 100%;
  font-family: var(--font-mono);
}

/* 工具栏 */
.toolbar {
  display: flex; align-items: center; gap: 12px;
  padding: 0 0 12px; border-bottom: 1px solid var(--color-orbit-border);
}
.toolbar-right {
  display: flex; align-items: center; gap: 12px; margin-left: auto;
}
.stats-badge {
  font-size: 11px; color: var(--color-orbit-text-muted);
  white-space: nowrap;
}

/* 主区域——画布+详情 */
.main-area {
  flex: 1; display: grid;
  grid-template-columns: 1fr 280px; gap: 12px;
  min-height: 0; margin-top: 12px;
}
.canvas-area { min-height: 0; overflow: hidden; }
.detail-area {
  min-height: 0; overflow-y: auto;
  border-left: 1px solid var(--color-orbit-border);
}

/* 状态覆盖 */
.state-overlay {
  grid-column: 1 / -1;
  display: flex; flex-direction: column; align-items: center; justify-content: center;
  gap: 12px; color: var(--color-orbit-text-secondary);
}
.empty-icon { font-size: 40px; }
.state-overlay h3 { font-size: 16px; margin: 0; color: #e0e0e0; }
.state-overlay p { font-size: 13px; color: var(--color-orbit-text-muted); margin: 0; }
.spinner {
  width: 32px; height: 32px; border: 3px solid var(--color-orbit-border);
  border-top-color: var(--color-orbit-accent); border-radius: 50%;
  animation: spin 0.8s linear infinite;
}
@keyframes spin { to { transform: rotate(360deg); } }
.retry-btn {
  padding: 8px 20px; background: var(--color-orbit-accent); color: #fff;
  border: none; border-radius: 4px; cursor: pointer; font-family: inherit;
}
.retry-btn:hover { opacity: 0.85; }
</style>
