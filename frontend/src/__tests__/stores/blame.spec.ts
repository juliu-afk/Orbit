import { describe, it, expect, beforeEach, vi, afterEach } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import { useBlameStore } from '@/stores/blame'

describe('Blame Store(PR5)', () => {
  beforeEach(() => { setActivePinia(createPinia()) })
  afterEach(() => { vi.restoreAllMocks() })

  it('fetchBlame 解析裸数组', async () => {
    const rows = [
      { author: 'Alice <a@x.com>', time: '1700000000', is_agent: false, content: 'x = 1' },
      { author: 'Bot <noreply@github.com>', time: '1700000001', is_agent: true, content: 'y = 2' },
    ]
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, json: () => Promise.resolve(rows) }))
    const store = useBlameStore()
    await store.fetchBlame('a.py')
    expect(store.currentFile).toBe('a.py')
    expect(store.lines).toHaveLength(2)
    expect(store.lines[1].is_agent).toBe(true)
  })

  it('fetchBlame 失败降级空数组', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: false, json: () => Promise.resolve(null) }))
    const store = useBlameStore()
    await store.fetchBlame('missing.py')
    expect(store.lines).toEqual([])
  })
})
