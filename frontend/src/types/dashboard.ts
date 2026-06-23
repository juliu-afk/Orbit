/** Dashboard 数据类型定义。
 *
 * 与后端 WebSocket 推送 payload 结构对齐。
 * 字段来源：src/orbit/events/schemas.py
 */

/** DAG 节点状态（对应后端 NodeStatus） */
export type NodeStatus = 'pending' | 'running' | 'success' | 'failed' | 'skipped'

/** DAG 节点 */
export interface DagNode {
  id: string
  agent_role: string
  status: NodeStatus
  duration_ms: number | null
  error: string | null
}

/** 告警严重级别 */
export type AlertSeverity = 'warning' | 'critical'

/** 告警条目 */
export interface Alert {
  task_id: string
  level: string
  severity: AlertSeverity
  message: string
  timestamp: string
}

/** Token 数据点（单个时间点） */
export interface TokenPoint {
  timestamp: string
  prompt_tokens: number
  completion_tokens: number
  total_tokens: number
}

/** WebSocket 推送消息基类 */
export interface WsMessage {
  type: 'task:update' | 'token:update' | 'alert:new' | 'error'
  task_id: string
  payload: Record<string, unknown>
  timestamp: string
}

/** C→S 客户端消息 */
export interface ClientMessage {
  type: 'subscribe' | 'unsubscribe'
  task_id: string
}
