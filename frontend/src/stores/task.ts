/** 任务状态 + DAG 拓扑数据。
 *
 * 消费 WebSocket 'task:update' 事件，更新任务状态和 DAG 节点。
 * visData getter 直接输出 vis-network 可消费的数据格式。
 */
import { defineStore } from 'pinia'
import { computed, ref } from 'vue'
import type { DagNode, NodeStatus } from '@/types/dashboard'

/** vis-network 节点数据格式 */
interface VisNode {
  id: string
  label: string
  color: string
  shape: string
}

/** vis-network 边数据格式 */
interface VisEdge {
  from: string
  to: string
  color: string
  arrows: string
}

/** 节点颜色映射 */
const STATUS_COLORS: Record<NodeStatus, string> = {
  pending: '#909399',
  running: '#E6A23C',
  success: '#67C23A',
  failed: '#F56C6C',
  skipped: '#C0C4CC',
}

export const useTaskStore = defineStore('task', () => {
  const taskState = ref<string>('IDLE')
  const progress = ref<number>(0)
  const dagNodes = ref<Map<string, DagNode>>(new Map())
  const dagEdges = ref<Array<{ from: string; to: string }>>([])

  /** 转换为 vis-network 消费的格式 */
  const visData = computed<{ nodes: VisNode[]; edges: VisEdge[] }>(() => {
    const nodes: VisNode[] = []
    for (const [id, node] of dagNodes.value) {
      nodes.push({
        id,
        label: `${node.agent_role || id}\n${node.status}`,
        color: STATUS_COLORS[node.status] || '#909399',
        shape: node.status === 'running' ? 'dot' : 'box',
      })
    }
    const edges: VisEdge[] = dagEdges.value.map((e) => ({
      from: e.from,
      to: e.to,
      color: '#909399',
      arrows: 'to',
    }))
    return { nodes, edges }
  })

  function handleTaskUpdate(payload: Record<string, unknown>) {
    taskState.value = (payload.state as string) || taskState.value
    progress.value = (payload.progress as number) ?? progress.value

    // 解析 DAG 节点列表
    const dag = payload.dag as Array<Record<string, unknown>> | undefined
    if (dag && Array.isArray(dag)) {
      for (const raw of dag) {
        const node: DagNode = {
          id: raw.id as string,
          agent_role: (raw.agent_role as string) || 'unknown',
          status: (raw.status as NodeStatus) || 'pending',
          duration_ms: (raw.duration_ms as number) || null,
          error: (raw.error as string) || null,
        }
        dagNodes.value.set(node.id, node)
      }
    }
    // 简单假设：DAG 边由后端维护，当前 MVP 仅推送节点
  }

  function reset() {
    taskState.value = 'IDLE'
    progress.value = 0
    dagNodes.value.clear()
    dagEdges.value = []
  }

  return { taskState, progress, dagNodes, dagEdges, visData, handleTaskUpdate, reset }
})
