import { describe, it, expect, beforeEach, vi, afterEach } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'

vi.mock('@/services/api', () => ({ apiGet: vi.fn(), apiPost: vi.fn(), apiDelete: vi.fn() }))
import { apiGet, apiPost, apiDelete } from '@/services/api'
import { useLoopStore } from '@/stores/loop'

describe('Loop Store(PR4)', () => {
  beforeEach(() => { setActivePinia(createPinia()) })
  afterEach(() => { vi.restoreAllMocks() })

  it('fetchLoops 解析列表', async () => {
    vi.mocked(apiGet).mockResolvedValue({
      loops: [{ id: 'a', interval_seconds: 300, command: 'echo hi', status: 'active', run_count: 2 }],
      total: 1,
    })
    const store = useLoopStore()
    await store.fetchLoops()
    expect(store.loops).toHaveLength(1)
    expect(store.loops[0].command).toBe('echo hi')
  })

  it('fetchLoops 失败降级空列表', async () => {
    vi.mocked(apiGet).mockRejectedValue(new Error('fail'))
    const store = useLoopStore()
    await store.fetchLoops()
    expect(store.loops).toEqual([])
    expect(store.error).toBe('加载定时任务失败')
  })

  it('createLoop 调 POST 后刷新', async () => {
    vi.mocked(apiPost).mockResolvedValue({})
    vi.mocked(apiGet).mockResolvedValue({ loops: [], total: 0 })
    const store = useLoopStore()
    await store.createLoop('5m', 'ls')
    expect(apiPost).toHaveBeenCalledWith('/api/v1/loop', { interval: '5m', command: 'ls' })
    expect(apiGet).toHaveBeenCalled()
  })

  it('pause/resume/stop 调对应端点', async () => {
    vi.mocked(apiPost).mockResolvedValue({})
    vi.mocked(apiDelete).mockResolvedValue({})
    vi.mocked(apiGet).mockResolvedValue({ loops: [], total: 0 })
    const store = useLoopStore()
    await store.pauseLoop('x')
    expect(apiPost).toHaveBeenCalledWith('/api/v1/loop/x/pause', {})
    await store.resumeLoop('x')
    expect(apiPost).toHaveBeenCalledWith('/api/v1/loop/x/resume', {})
    await store.stopLoop('x')
    expect(apiDelete).toHaveBeenCalledWith('/api/v1/loop/x')
  })
})
