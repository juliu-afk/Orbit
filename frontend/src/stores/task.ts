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
  const currentTaskId = ref<string>('')
  const dagNodes = ref<Map<string, DagNode>>(new Map())
  const dagEdges = ref<Array<{ from: string; to: string }>>([])
  const codeOutput = ref<string | null>(null)
  const hasCodeOutput = ref(false)

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
    // PR3: 捕获当前 task_id，供取消用
    if (typeof payload.task_id === 'string' && payload.task_id) currentTaskId.value = payload.task_id

    // 提取代码产物——CODING/DONE 状态时后端推送生成的代码
    if (payload.output && typeof payload.output === 'string') {
      codeOutput.value = payload.output
      hasCodeOutput.value = true
    }

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
  }

  function consumeCodeOutput() {
    hasCodeOutput.value = false
  }

  // PR3: 取消当前运行中任务——调真实调度器 cancel（写 CANCELLED 检查点 + 停止 asyncio 任务）。
  // P2-3: tasks 端点返回裸 TaskStatusResponse(非 {code,data} 包装, apiPost 会抛错)，用原生 fetch；
  // taskState 用后端响应的真实状态而非硬写 CANCELLED。
  async function cancelCurrentTask(): Promise<void> {
    if (!currentTaskId.value) return
    const r = await fetch(`/api/v1/tasks/${currentTaskId.value}/cancel`, { method: 'POST' })
    if (!r.ok) throw new Error(`取消失败 (HTTP ${r.status})`)
    const data = await r.json()
    taskState.value = data.state || 'CANCELLED'
  }

  function reset() {
    taskState.value = 'IDLE'
    progress.value = 0
    currentTaskId.value = ''
    dagNodes.value.clear()
    dagEdges.value = []
    codeOutput.value = null
    hasCodeOutput.value = false
  }

  return { taskState, progress, currentTaskId, dagNodes, dagEdges, visData,
    codeOutput, hasCodeOutput, handleTaskUpdate, consumeCodeOutput, cancelCurrentTask, reset }
})
