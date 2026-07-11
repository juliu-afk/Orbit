import { describe, it, expect, beforeEach, vi, afterEach } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import { useTaskStore } from '@/stores/task'

// PR3: 取消当前任务 + 捕获 task_id（cancel 走原生 fetch，读后端真实 state）
describe('Task Store — cancel(PR3)', () => {
  beforeEach(() => { setActivePinia(createPinia()) })
  afterEach(() => { vi.restoreAllMocks() })

  it('handleTaskUpdate 捕获 task_id', () => {
    const store = useTaskStore()
    store.handleTaskUpdate({ state: 'PARSING', progress: 0.2, task_id: 'abc123' })
    expect(store.currentTaskId).toBe('abc123')
  })

  it('cancelCurrentTask 调 cancel 端点并采用后端返回 state', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, json: () => Promise.resolve({ state: 'CANCELLED' }) }))
    const store = useTaskStore()
    store.handleTaskUpdate({ state: 'CODING', task_id: 't9' })
    await store.cancelCurrentTask()
    expect(fetch).toHaveBeenCalledWith('/api/v1/tasks/t9/cancel', { method: 'POST' })
    expect(store.taskState).toBe('CANCELLED')
  })

  it('cancelCurrentTask 无 task_id 时不调用', async () => {
    const fetchMock = vi.fn()
    vi.stubGlobal('fetch', fetchMock)
    const store = useTaskStore()
    await store.cancelCurrentTask()
    expect(fetchMock).not.toHaveBeenCalled()
  })

  it('cancelCurrentTask HTTP 错误抛出', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: false, status: 500 }))
    const store = useTaskStore()
    store.handleTaskUpdate({ state: 'CODING', task_id: 't1' })
    await expect(store.cancelCurrentTask()).rejects.toThrow(/500/)
  })
})
