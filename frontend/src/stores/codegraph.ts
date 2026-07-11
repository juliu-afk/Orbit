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

  // 测试覆盖空洞（PR6）
  const testGaps = ref<TestGapsData | null>(null)
  const testGapsLoading = ref(false)

  // 大纲 / 影响分析（PR2 接线）
  const outline = ref<OutlineItem[]>([])
  const impact = ref<ImpactNode[]>([])
  const impactSymbol = ref('')

  // 历史快照时间轴（PR10）
  const commits = ref<Array<{ hash: string; message: string; author: string; date: string }>>([])
  const viewingCommit = ref<string>('')  // 空 = 当前版本

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

  // PR10: 拉取 git commit 列表（时间轴滑块数据源）
  async function fetchCommits(): Promise<void> {
    try {
      const data = await apiGet<{ commits: Array<{ hash: string; message: string; author: string; date: string }> }>('/api/v1/codegraph/git-commits?limit=50')
      commits.value = data.commits || []
    } catch {
      commits.value = []
    }
  }

  // PR10: 切换到指定 commit 的历史图谱（隔离构建，慢，需 loading）
  async function fetchGraphAt(commit: string): Promise<void> {
    loading.value = true
    error.value = null
    viewingCommit.value = commit
    try {
      const data = await apiGet<GraphDataResponse>(`/api/v1/codegraph/graph-data-at?commit=${encodeURIComponent(commit)}`)
      elements.value = data.elements
      stats.value = data.stats
    } catch (e) {
      error.value = '历史图谱构建失败：' + (e instanceof Error ? e.message : String(e))
      elements.value = []
    } finally {
      loading.value = false
    }
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

  // WHY 用原生 fetch 而非 apiGet：outline/impact 端点返回裸数组（非 {code,data} 包装），
  // apiGet 会因 json.code!==0 抛错。这两个端点契约就是裸 list，直接解析。
  // P2-1: 加 10s 超时——后端挂起时 abort，避免请求永久 pending 卡住后续触发。
  async function _fetchList(url: string): Promise<unknown[]> {
    const ctrl = new AbortController()
    const timer = setTimeout(() => ctrl.abort(), 10000)
    try {
      const r = await fetch(url, { signal: ctrl.signal })
      return r.ok ? await r.json() : []
    } catch {
      return []
    } finally {
      clearTimeout(timer)
    }
  }

  async function fetchOutline(file: string): Promise<void> {
    outline.value = (await _fetchList(`/api/v1/codegraph/outline?file=${encodeURIComponent(file)}`)) as OutlineItem[]
  }

  async function fetchImpact(symbol: string): Promise<void> {
    impactSymbol.value = symbol
    impact.value = (await _fetchList(`/api/v1/insights/impact?symbol=${encodeURIComponent(symbol)}`)) as ImpactNode[]
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
    outline.value = []
    impact.value = []
    impactSymbol.value = ''
    commits.value = []
    viewingCommit.value = ''
  }

  return {
    elements, stats, loading, error,
    selectedNodeId, searchQuery, activeLayout, visibleEdgeTypes,
    testGaps, testGapsLoading,
    outline, impact, impactSymbol,
    commits, viewingCommit,
    nodes, edges,
    fetchGraphData, selectNode, setSearchQuery, setLayout, toggleEdgeType, reset,
    fetchTestGaps, fetchOutline, fetchImpact,
    fetchCommits, fetchGraphAt,
  }
})
