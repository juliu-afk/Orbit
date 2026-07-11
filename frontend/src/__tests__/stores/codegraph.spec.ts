import { describe, it, expect, beforeEach, vi, afterEach } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import { useCodeGraphStore } from '@/stores/codegraph'

// PR2: outline/impact 接线——store 用原生 fetch（端点返回裸数组）
describe('CodeGraph Store — outline/impact 接线', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })
  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('fetchOutline 解析裸数组到 outline', async () => {
    const items = [{ name: 'Foo', kind: 'class', line: 1 }, { name: 'bar', kind: 'function', line: 10 }]
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, json: () => Promise.resolve(items) }))
    const store = useCodeGraphStore()
    await store.fetchOutline('a.py')
    expect(store.outline).toHaveLength(2)
    expect(store.outline[0].name).toBe('Foo')
  })

  it('fetchOutline 失败时降级为空数组', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: false, json: () => Promise.resolve(null) }))
    const store = useCodeGraphStore()
    await store.fetchOutline('missing.py')
    expect(store.outline).toEqual([])
  })

  it('fetchImpact 记录 symbol 并解析节点', async () => {
    const nodes = [{ name: 'caller', file: 'x.py', level: 'direct', callers: [] }]
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, json: () => Promise.resolve(nodes) }))
    const store = useCodeGraphStore()
    await store.fetchImpact('my_func')
    expect(store.impactSymbol).toBe('my_func')
    expect(store.impact).toHaveLength(1)
    expect(store.impact[0].level).toBe('direct')
  })

  it('reset 清空 outline/impact', async () => {
    const store = useCodeGraphStore()
    store.outline = [{ name: 'x', kind: 'function', line: 1 }]
    store.impact = [{ name: 'y', file: '', level: 'direct', callers: [] }]
    store.reset()
    expect(store.outline).toEqual([])
    expect(store.impact).toEqual([])
    expect(store.impactSymbol).toBe('')
  })
})
