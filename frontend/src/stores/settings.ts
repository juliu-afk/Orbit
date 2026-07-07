import { defineStore } from 'pinia'
import { ref, watch } from 'vue'
import { getCurrentLocale, setLocale } from '@/i18n'

export interface UserSettings {
  theme: 'dark' | 'light'; fileTreeLeft: boolean; agentRight: boolean
  glassOpacity: number; glassBlur: number; fileTreeWidth: number; rightPanelWidth: number
  locale: 'zh-CN' | 'en'
}
const DEFAULTS: UserSettings = { theme: 'dark', fileTreeLeft: true, agentRight: true, glassOpacity: 45, glassBlur: 4, fileTreeWidth: 240, rightPanelWidth: 260, locale: 'zh-CN' }
const STORAGE_KEY = 'orbit-settings'
function load(): UserSettings { try { const r = localStorage.getItem(STORAGE_KEY); if (r) return { ...DEFAULTS, ...JSON.parse(r) } } catch { /* corrupt */ } return { ...DEFAULTS } }
function save(s: UserSettings) { localStorage.setItem(STORAGE_KEY, JSON.stringify(s)) }

export const useSettingsStore = defineStore('settings', () => {
  const saved = load()
  const theme = ref<'dark' | 'light'>(saved.theme); const fileTreeLeft = ref(saved.fileTreeLeft)
  const agentRight = ref(saved.agentRight); const glassOpacity = ref(saved.glassOpacity)
  const glassBlur = ref(saved.glassBlur); const fileTreeWidth = ref(saved.fileTreeWidth)
  const rightPanelWidth = ref(saved.rightPanelWidth)
  const locale = ref<'zh-CN' | 'en'>(saved.locale || 'zh-CN')

  function applyTheme(t: 'dark' | 'light') { document.documentElement.dataset.theme = t; theme.value = t }
  function applyGlass() {
    document.documentElement.style.setProperty('--glass-opacity', `${glassOpacity.value / 100}`)
    document.documentElement.style.setProperty('--glass-blur', `${glassBlur.value}px`)
  }
  function applyPanelWidths() {
    document.documentElement.style.setProperty('--spacing-filetree', `${fileTreeWidth.value}px`)
    document.documentElement.style.setProperty('--spacing-right-panel', `${rightPanelWidth.value}px`)
  }
  function applyLocale(l: 'zh-CN' | 'en') { locale.value = l; setLocale(l) }
  // WHY 初始化时同步 i18n 实例: main.ts 可能在 store 之前创建 i18n
  if (saved.locale && saved.locale !== getCurrentLocale()) setLocale(saved.locale)
  applyTheme(theme.value); applyGlass(); applyPanelWidths()

  watch(() => ({ t: theme.value, fl: fileTreeLeft.value, ar: agentRight.value, go: glassOpacity.value, gb: glassBlur.value, ft: fileTreeWidth.value, rp: rightPanelWidth.value, l: locale.value }), (s) => {
    save(s as unknown as UserSettings); applyTheme(s.t); applyGlass(); applyPanelWidths(); applyLocale(s.l)
  }, { deep: true })

  function resetDefaults() {
    applyTheme(DEFAULTS.theme); fileTreeLeft.value = DEFAULTS.fileTreeLeft; agentRight.value = DEFAULTS.agentRight
    glassOpacity.value = DEFAULTS.glassOpacity; glassBlur.value = DEFAULTS.glassBlur
    fileTreeWidth.value = DEFAULTS.fileTreeWidth; rightPanelWidth.value = DEFAULTS.rightPanelWidth
    locale.value = DEFAULTS.locale
    applyGlass(); applyPanelWidths(); applyLocale(DEFAULTS.locale)
    save(DEFAULTS)  // P2 fix: 显式写 localStorage
  }
  return { theme, fileTreeLeft, agentRight, glassOpacity, glassBlur, fileTreeWidth, rightPanelWidth, locale, applyTheme, applyGlass, applyPanelWidths, applyLocale, resetDefaults }
})
