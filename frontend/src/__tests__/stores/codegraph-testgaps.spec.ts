import { describe, it, expect, beforeEach, vi, afterEach } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'

// PR6: test-gaps 是 {code,data} 包装，store 用 apiGet
vi.mock('@/services/api', () => ({ apiGet: vi.fn() }))
import { apiGet } from '@/services/api'
import { useCodeGraphStore } from '@/stores/codegraph'

describe('CodeGraph Store — test-gaps(PR6)', () => {
  beforeEach(() => setActivePinia(createPinia()))
  afterEach(() => vi.restoreAllMocks())

  it('fetchTestGaps 解析空洞数据', async () => {
    vi.mocked(apiGet).mockResolvedValue({
      function: 'my_func',
      gaps: [{ param: 'x', type: 'int', covered: ['0'], missing: ['负数', '大数'] }],
      total: 1,
    })
    const store = useCodeGraphStore()
    await store.fetchTestGaps('my_func')
    expect(store.testGaps?.function).toBe('my_func')
    expect(store.testGaps?.gaps).toHaveLength(1)
    expect(store.testGaps?.gaps[0].missing).toContain('负数')
  })

  it('fetchTestGaps 失败时降级', async () => {
    vi.mocked(apiGet).mockRejectedValue(new Error('fail'))
    const store = useCodeGraphStore()
    await store.fetchTestGaps('bad')
    expect(store.testGaps?.total).toBe(0)
    expect(store.testGaps?.message).toBe('查询失败')
  })

  it('reset 清空 testGaps', async () => {
    const store = useCodeGraphStore()
    store.testGaps = { function: 'x', gaps: [], total: 0 }
    store.reset()
    expect(store.testGaps).toBeNull()
  })
})
