// P2-2: settings 持久化回归测试——watch 键名不匹配导致刷新丢失
import { describe, it, expect, beforeEach } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'

const STORAGE_KEY = 'orbit-settings'

describe('settings persistence', () => {
  beforeEach(() => {
    // 清 localStorage + 重建 Pinia 实例——每次测试独立
    localStorage.clear()
    setActivePinia(createPinia())
    // 重置 DOM dataset（applyTheme 副作用）
    document.documentElement.dataset.theme = ''
  })

  it('loads defaults when localStorage is empty', async () => {
    const { useSettingsStore } = await import('./settings')
    const store = useSettingsStore()
    expect(store.theme).toBe('dark')
    expect(store.locale).toBe('zh-CN')
    expect(store.fileTreeLeft).toBe(true)
  })

  it('persists theme change to localStorage', async () => {
    const { useSettingsStore } = await import('./settings')
    const store = useSettingsStore()
    store.theme = 'light'
    // Vue watcher 异步写 localStorage——等一帧
    await new Promise(r => setTimeout(r, 10))
    const raw = localStorage.getItem(STORAGE_KEY)
    expect(raw).not.toBeNull()
    const parsed = JSON.parse(raw!)
    expect(parsed.theme).toBe('light')
  })

  it('restores saved settings on reload (regression: key name mismatch)', async () => {
    // 模拟上次保存的 settings——必须用完整 UserSettings 键名
    localStorage.setItem(STORAGE_KEY, JSON.stringify({
      theme: 'light',
      fileTreeLeft: false,
      agentRight: false,
      glassOpacity: 55,
      glassBlur: 8,
      fileTreeWidth: 300,
      rightPanelWidth: 350,
      locale: 'en',
    }))
    const { useSettingsStore } = await import('./settings')
    const store = useSettingsStore()
    expect(store.theme).toBe('light')          // 回归: 缩写键 "t" 不会覆盖 DEFAULTS.theme
    expect(store.locale).toBe('en')            // 回归: 缩写键 "l" 不会覆盖 DEFAULTS.locale
    expect(store.fileTreeLeft).toBe(false)
    expect(store.glassOpacity).toBe(55)
  })

  it('rejects old short-key format gracefully (migration safety)', async () => {
    // 旧版写入的缩写键格式——应被忽略，回退 DEFAULTS
    localStorage.setItem(STORAGE_KEY, JSON.stringify({
      t: 'light',
      fl: false,
      ar: false,
      go: 55,
      gb: 8,
      ft: 300,
      rp: 350,
      l: 'en',
    }))
    const { useSettingsStore } = await import('./settings')
    const store = useSettingsStore()
    // 缩写键不匹配任何 UserSettings 键 → spread 无效 → DEFAULTS
    expect(store.theme).toBe('dark')
    expect(store.locale).toBe('zh-CN')
  })
})
