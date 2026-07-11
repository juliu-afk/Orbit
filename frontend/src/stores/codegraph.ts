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

// 大纲项（对应后端 /codegraph/outline，OutlinePanel props）
export interface OutlineItem {
  name: string
  kind: string
  line: number
  children?: OutlineItem[]
}

// 影响节点（对应后端 /insights/impact，ImpactGraph props）
export interface ImpactNode {
  name: string
  file: string
  level: string
  callers: string[]
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

  // 大纲 / 影响分析（PR2 接线）
  const outline = ref<OutlineItem[]>([])
  const impact = ref<ImpactNode[]>([])
  const impactSymbol = ref('')

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

  // WHY 用原生 fetch 而非 apiGet：outline/impact 端点返回裸数组（非 {code,data} 包装），
  // apiGet 会因 json.code!==0 抛错。这两个端点契约就是裸 list，直接解析。
  async function fetchOutline(file: string): Promise<void> {
    try {
      const r = await fetch(`/api/v1/codegraph/outline?file=${encodeURIComponent(file)}`)
      outline.value = r.ok ? await r.json() : []
    } catch {
      outline.value = []
    }
  }

  async function fetchImpact(symbol: string): Promise<void> {
    impactSymbol.value = symbol
    try {
      const r = await fetch(`/api/v1/insights/impact?symbol=${encodeURIComponent(symbol)}`)
      impact.value = r.ok ? await r.json() : []
    } catch {
      impact.value = []
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
    outline.value = []
    impact.value = []
    impactSymbol.value = ''
  }

  return {
    elements, stats, loading, error,
    selectedNodeId, searchQuery, activeLayout, visibleEdgeTypes,
    outline, impact, impactSymbol,
    nodes, edges,
    fetchGraphData, selectNode, setSearchQuery, setLayout, toggleEdgeType, reset,
    fetchOutline, fetchImpact,
  }
})
