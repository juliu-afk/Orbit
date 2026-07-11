import { describe, it, expect, beforeEach, vi, afterEach } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'

vi.mock('@/services/api', () => ({ apiGet: vi.fn() }))
import { apiGet } from '@/services/api'
import { useCodeGraphStore } from '@/stores/codegraph'

// PR10: 历史快照时间轴
describe('CodeGraph Store — snapshots(PR10)', () => {
  beforeEach(() => { setActivePinia(createPinia()) })
  afterEach(() => { vi.restoreAllMocks() })

  it('fetchCommits 解析 commit 列表', async () => {
    vi.mocked(apiGet).mockResolvedValue({
      commits: [{ hash: 'abc1234', message: 'init', author: 'T', date: '2026-01-01' }],
    })
    const store = useCodeGraphStore()
    await store.fetchCommits()
    expect(store.commits).toHaveLength(1)
    expect(store.commits[0].message).toBe('init')
  })

  it('fetchGraphAt 切换历史图谱并记录 viewingCommit', async () => {
    vi.mocked(apiGet).mockResolvedValue({
      elements: [{ data: { id: 'code:1' } }],
      stats: { node_count: 1, edge_count: 0, commit: 'abc' },
    })
    const store = useCodeGraphStore()
    await store.fetchGraphAt('abc1234')
    expect(store.viewingCommit).toBe('abc1234')
    expect(store.elements).toHaveLength(1)
  })

  it('fetchGraphAt 失败降级空图', async () => {
    vi.mocked(apiGet).mockRejectedValue(new Error('build failed'))
    const store = useCodeGraphStore()
    await store.fetchGraphAt('bad')
    expect(store.elements).toEqual([])
    expect(store.error).toContain('历史图谱')
  })

  it('reset 清空时间轴', async () => {
    const store = useCodeGraphStore()
    store.commits = [{ hash: 'x', message: 'm', author: 'a', date: 'd' }]
    store.viewingCommit = 'x'
    store.reset()
    expect(store.commits).toEqual([])
    expect(store.viewingCommit).toBe('')
  })
})
