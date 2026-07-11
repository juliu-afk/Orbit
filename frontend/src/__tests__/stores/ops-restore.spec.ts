import { describe, it, expect, beforeEach, vi, afterEach } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import { useOpsStore } from '@/stores/ops'

// PR9: 恢复用原生 fetch POST /backup/restore
describe('Ops Store — restore(PR9)', () => {
  beforeEach(() => { setActivePinia(createPinia()) })
  afterEach(() => { vi.restoreAllMocks() })

  it('restoreSnapshot 成功时 POST 正确 body', async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce({ ok: true, json: () => Promise.resolve({ code: 0, data: { restored: true } }) })
      .mockResolvedValueOnce({ ok: true, json: () => Promise.resolve({ code: 0, data: [] }) })  // fetchSnapshots 刷新
    vi.stubGlobal('fetch', fetchMock)
    const store = useOpsStore()
    await store.restoreSnapshot('snap-1', 'data/orbit.db')
    const [url, opts] = fetchMock.mock.calls[0]
    expect(url).toBe('/api/v1/backup/restore')
    expect(JSON.parse(opts.body)).toEqual({ snapshot_id: 'snap-1', target_path: 'data/orbit.db' })
  })

  it('restoreSnapshot 后端 code!=0 抛错', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, json: () => Promise.resolve({ code: 500, message: '恢复失败' }) }))
    const store = useOpsStore()
    await expect(store.restoreSnapshot('snap-1', 'data/orbit.db')).rejects.toThrow('恢复失败')
  })

  it('restoreSnapshot HTTP 错误抛错', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: false, status: 404, json: () => Promise.resolve({}) }))
    const store = useOpsStore()
    await expect(store.restoreSnapshot('x', 'y')).rejects.toThrow(/404/)
  })
})
