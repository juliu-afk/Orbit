import { describe, it, expect, beforeEach } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import { useTaskStore } from '@/stores/task'

describe('Task Store', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it('初始状态为 IDLE', () => {
    const store = useTaskStore()
    expect(store.taskState).toBe('IDLE')
    expect(store.progress).toBe(0)
    expect(store.dagNodes.size).toBe(0)
  })

  it('handleTaskUpdate 更新 state 和 progress', () => {
    const store = useTaskStore()
    store.handleTaskUpdate({ state: 'CODING', progress: 0.5, dag: [] })
    expect(store.taskState).toBe('CODING')
    expect(store.progress).toBe(0.5)
  })

  it('handleTaskUpdate 解析 DAG 节点', () => {
    const store = useTaskStore()
    store.handleTaskUpdate({
      state: 'CODING',
      progress: 0.5,
      dag: [
        { id: 'n1', agent_role: 'developer', status: 'running', duration_ms: null, error: null },
        { id: 'n2', agent_role: 'reviewer', status: 'pending', duration_ms: null, error: null },
      ],
    })
    expect(store.dagNodes.size).toBe(2)
    expect(store.dagNodes.get('n1')?.status).toBe('running')
    expect(store.dagNodes.get('n2')?.agent_role).toBe('reviewer')
  })

  it('visData getter 转换格式正确', () => {
    const store = useTaskStore()
    store.handleTaskUpdate({
      state: 'RUNNING',
      progress: 0.3,
      dag: [{ id: 'x1', agent_role: 'architect', status: 'running', duration_ms: null, error: null }],
    })
    const data = store.visData
    expect(data.nodes).toHaveLength(1)
    expect(data.nodes[0].id).toBe('x1')
    expect(data.nodes[0].color).toBe('#E6A23C') // running = yellow
    expect(data.nodes[0].shape).toBe('dot')       // running = dot (pulsing)
  })

  it('reset 清空所有状态', () => {
    const store = useTaskStore()
    store.handleTaskUpdate({ state: 'DONE', progress: 1.0, dag: [{ id: 'x', agent_role: 'dev', status: 'success', duration_ms: null, error: null }] })
    store.reset()
    expect(store.taskState).toBe('IDLE')
    expect(store.progress).toBe(0)
    expect(store.dagNodes.size).toBe(0)
  })
})
