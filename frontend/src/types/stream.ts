/** SSE 流式事件类型——匹配后端 StreamEventType 枚举.

 * WHY 独立类型文件: composable 和组件共用事件类型定义，
 * 避免字符串硬编码造成前后端不一致。
 */
export type StreamEventType =
  | 'text_delta'
  | 'thinking'
  | 'tool_call'
  | 'tool_result'
  | 'turn_start'
  | 'finish_step'
  | 'error'
  | 'cancelled'

/** SSE 事件格式——匹配后端 StreamEvent Pydantic 模型. */
export interface StreamEvent {
  type: StreamEventType
  taskId: string
  agentId: string
  turn: number
  data: Record<string, unknown>
}
