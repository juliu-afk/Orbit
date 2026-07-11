<!-- 代码图谱大尺寸抽屉——85% 宽度，三区布局（工具栏 | 画布 | 详情面板）。
     WHY 85% 而非 600px：代码图谱需要大面积画布，DAG 的 600px 太窄。 -->
<script setup lang="ts">
import { watch, ref } from 'vue'
import { useSessionStore } from '@/stores/session'
import { useCodeGraphStore } from '@/stores/codegraph'
import { apiPost } from '@/services/api'
import CytoscapeCanvas from './CytoscapeCanvas.vue'
import SearchBar from './SearchBar.vue'
import LayoutSelector from './LayoutSelector.vue'
import NodePanel from './NodePanel.vue'
import ImpactGraph from '@/components/insights/ImpactGraph.vue'

const props = defineProps<{ show: boolean }>()
const emit = defineEmits<{ (e: 'update:show', v: boolean): void }>()

const session = useSessionStore()
const store = useCodeGraphStore()
const building = ref(false)

// PR2: 选中节点 → 拉该符号的影响分析。symbol 取节点 label/name。
// P2-2: 防抖 300ms——图中快速切换节点时只取最后一次，避免请求洪峰。
// P2-3: String() 强转比较——节点 id 后端可能是 number，严格 === 会漏匹配。
let _impactTimer: ReturnType<typeof setTimeout> | undefined
watch(() => store.selectedNodeId, (id) => {
  if (_impactTimer) clearTimeout(_impactTimer)
  if (!id) { store.impact = []; return }
  _impactTimer = setTimeout(() => {
    const node = store.elements.find(e => String(e.data.id) === String(id))
    const symbol = (node?.data.label || node?.data.name || '') as string
    if (symbol) store.fetchImpact(symbol)
  }, 300)
})

// 打开抽屉时加载数据
watch(() => props.show, async (visible) => {
  if (visible && session.currentProjectName) {
    await store.fetchGraphData(session.currentProjectName)
    store.fetchCommits()  // PR10: 加载时间轴 commit 列表
  }
})

// PR10: 时间轴滑块——index 0 = 当前版本；>0 = 历史 commit（隔离构建，慢）
const timelineIdx = ref(0)
async function onTimelineChange(idx: number) {
  timelineIdx.value = idx
  if (idx === 0) {
    store.viewingCommit = ''
    await store.fetchGraphData(session.currentProjectName || '')
  } else {
    const commit = store.commits[idx - 1]
    if (commit) await store.fetchGraphAt(commit.hash)
  }
}

async function buildIndex(): Promise<void> {
  building.value = true
  try {
    const dir = session.currentProjectPath || session.currentProjectName
    await apiPost('/api/v1/codegraph/build', { directory: dir })
    // 重新加载图谱数据
    await store.fetchGraphData(session.currentProjectName)
  } catch (e) {
    store.error = e instanceof Error ? e.message : '索引构建失败'
  } finally {
    building.value = false
  }
}

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

      <!-- PR10: 历史时间轴——拖动查看图谱随 git commit 演进（0=当前，>0=历史，隔离构建） -->
      <div v-if="store.commits.length" class="timeline">
        <span class="timeline-label">
          {{ timelineIdx === 0 ? '当前版本' : (store.commits[timelineIdx - 1]?.message || '').slice(0, 40) }}
        </span>
        <el-slider
          :model-value="timelineIdx"
          :min="0"
          :max="store.commits.length"
          :format-tooltip="(v: number) => v === 0 ? '当前' : (store.commits[v - 1]?.hash || '').slice(0, 8)"
          style="flex:1;margin:0 12px"
          @change="onTimelineChange"
        />
        <span v-if="store.loading && timelineIdx > 0" class="timeline-hint">构建历史图谱中…</span>
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
          <p>打开项目后需手动触发解析</p>
          <button class="retry-btn" :disabled="building" @click="buildIndex">
            {{ building ? '正在解析…' : '构建索引' }}
          </button>
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
            <!-- PR2: 选中节点的影响分析——被谁调用 -->
            <ImpactGraph v-if="store.selectedNodeId" :symbol="store.impactSymbol" :nodes="store.impact" />
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

/* PR10 时间轴 */
.timeline {
  display: flex; align-items: center; gap: 8px;
  padding: 8px 0 4px; font-family: var(--font-mono); font-size: 11px;
}
.timeline-label { min-width: 120px; color: var(--color-orbit-text-secondary); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.timeline-hint { color: var(--color-orbit-accent); white-space: nowrap; }

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
