import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { apiGet } from '@/services/api'

// Cytoscape elements 格式
export interface GraphElement {
  data: Record<string, unknown>
}

export interface GraphStats {
  node_count: number
  edge_count: number
  built_at: string | null
}

export interface GraphDataResponse {
  elements: GraphElement[]
  stats: GraphStats
}

// 测试覆盖空洞（对应后端 /codegraph/test-gaps）
export interface TestGap {
  param: string
  type: string
  covered: string[]
  missing: string[]
}

export interface TestGapsData {
  function: string
  gaps: TestGap[]
  total: number
  message?: string
}

export const useCodeGraphStore = defineStore('codegraph', () => {
  // ── 状态 ──
  const elements = ref<GraphElement[]>([])
  const stats = ref<GraphStats>({ node_count: 0, edge_count: 0, built_at: null })
  const loading = ref(false)
  const error = ref<string | null>(null)

  // 选中与过滤
  const selectedNodeId = ref<string | null>(null)
  const searchQuery = ref('')
  const activeLayout = ref('cose')            // cose | breadthfirst | concentric
  const visibleEdgeTypes = ref<string[]>([])  // 空 = 全部显示

  // 测试覆盖空洞（PR6）
  const testGaps = ref<TestGapsData | null>(null)
  const testGapsLoading = ref(false)

  // ── 计算 ──
  const nodes = computed(() => elements.value.filter(e => !e.data.id?.toString().startsWith('e:')))
  const edges = computed(() => elements.value.filter(e => e.data.id?.toString().startsWith('e:')))

  // ── 操作 ──

  async function fetchGraphData(projectId: string): Promise<void> {
    loading.value = true
    error.value = null
    try {
      const data = await apiGet<GraphDataResponse>(`/api/v1/codegraph/graph-data?project_id=${encodeURIComponent(projectId)}`)
      elements.value = data.elements
      stats.value = data.stats
    } catch (e) {
      error.value = e instanceof Error ? e.message : '加载图谱数据失败'
      elements.value = []
    } finally {
      loading.value = false
    }
  }

  function selectNode(nodeId: string | null): void {
    selectedNodeId.value = nodeId
  }

  // PR6: 拉取指定函数的测试覆盖空洞。test-gaps 端点是 {code,data} 包装，apiGet 可直接用。
  async function fetchTestGaps(func: string): Promise<void> {
    testGapsLoading.value = true
    try {
      testGaps.value = await apiGet<TestGapsData>(`/api/v1/codegraph/test-gaps?function=${encodeURIComponent(func)}`)
    } catch {
      testGaps.value = { function: func, gaps: [], total: 0, message: '查询失败' }
    } finally {
      testGapsLoading.value = false
    }
  }

  function setSearchQuery(query: string): void {
    searchQuery.value = query
  }

  function setLayout(layout: string): void {
    activeLayout.value = layout
  }

  function toggleEdgeType(edgeType: string): void {
    const idx = visibleEdgeTypes.value.indexOf(edgeType)
    if (idx >= 0) {
      visibleEdgeTypes.value.splice(idx, 1)
    } else {
      visibleEdgeTypes.value.push(edgeType)
    }
  }

  function reset(): void {
    elements.value = []
    stats.value = { node_count: 0, edge_count: 0, built_at: null }
    loading.value = false
    error.value = null
    selectedNodeId.value = null
    searchQuery.value = ''
    testGaps.value = null
  }

  return {
    elements, stats, loading, error,
    selectedNodeId, searchQuery, activeLayout, visibleEdgeTypes,
    testGaps, testGapsLoading,
    nodes, edges,
    fetchGraphData, selectNode, setSearchQuery, setLayout, toggleEdgeType, reset,
    fetchTestGaps,
  }
})
