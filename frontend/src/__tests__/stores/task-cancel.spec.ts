import { describe, it, expect, beforeEach, vi, afterEach } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'

vi.mock('@/services/api', () => ({ apiPost: vi.fn() }))
import { apiPost } from '@/services/api'
import { useTaskStore } from '@/stores/task'

// PR3: 取消当前任务 + 捕获 task_id
describe('Task Store — cancel(PR3)', () => {
  beforeEach(() => { setActivePinia(createPinia()) })
  afterEach(() => { vi.restoreAllMocks() })

  it('handleTaskUpdate 捕获 task_id', () => {
    const store = useTaskStore()
    store.handleTaskUpdate({ state: 'PARSING', progress: 0.2, task_id: 'abc123' })
    expect(store.currentTaskId).toBe('abc123')
  })

  it('cancelCurrentTask 调 cancel 端点并置 CANCELLED', async () => {
    vi.mocked(apiPost).mockResolvedValue({})
    const store = useTaskStore()
    store.handleTaskUpdate({ state: 'CODING', task_id: 't9' })
    await store.cancelCurrentTask()
    expect(apiPost).toHaveBeenCalledWith('/api/v1/tasks/t9/cancel', {})
    expect(store.taskState).toBe('CANCELLED')
  })

  it('cancelCurrentTask 无 task_id 时不调用', async () => {
    const store = useTaskStore()
    await store.cancelCurrentTask()
    expect(apiPost).not.toHaveBeenCalled()
  })
})
