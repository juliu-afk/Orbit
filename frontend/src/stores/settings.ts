import { defineStore } from 'pinia'
import { ref, watch } from 'vue'

// WHY v0.23: 集中管理所有用户设置——主题/布局/透明度，统一持久化到 localStorage
export interface UserSettings {
  theme: 'dark' | 'light'
  fileTreeLeft: boolean      // true=左侧, false=右侧
  agentRight: boolean        // true=右侧, false=左侧
  glassOpacity: number       // 0-100, 默认 85
  glassBlur: number          // 0-24px, 默认 12
  fileTreeWidth: number      // px, 默认 240
  rightPanelWidth: number    // px, 默认 260
}

const DEFAULTS: UserSettings = {
  theme: 'dark',
  fileTreeLeft: true,
  agentRight: true,
  glassOpacity: 85,
  glassBlur: 12,
  fileTreeWidth: 240,
  rightPanelWidth: 260,
}

const STORAGE_KEY = 'orbit-settings'

function load(): UserSettings {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (raw) return { ...DEFAULTS, ...JSON.parse(raw) }
  } catch { /* corrupted data */ }
  return { ...DEFAULTS }
}

function save(s: UserSettings) {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(s))
}

export const useSettingsStore = defineStore('settings', () => {
  const saved = load()
  const theme = ref<'dark' | 'light'>(saved.theme)
  const fileTreeLeft = ref(saved.fileTreeLeft)
  const agentRight = ref(saved.agentRight)
  const glassOpacity = ref(saved.glassOpacity)
  const glassBlur = ref(saved.glassBlur)
  const fileTreeWidth = ref(saved.fileTreeWidth)
  const rightPanelWidth = ref(saved.rightPanelWidth)

  // WHY 自动持久化：任何设置变更立即写 localStorage + 更新 CSS 变量/DOM
  function applyTheme(t: 'dark' | 'light') {
    document.documentElement.dataset.theme = t
    theme.value = t
  }

  // P1-2 fix: 只设抽象变量，颜色由 CSS [data-theme] 决定
  function applyGlass() {
    document.documentElement.style.setProperty('--glass-opacity', `${glassOpacity.value / 100}`)
    document.documentElement.style.setProperty('--glass-blur', `${glassBlur.value}px`)
  }

  function applyPanelWidths() {
    document.documentElement.style.setProperty('--spacing-filetree', `${fileTreeWidth.value}px`)
    document.documentElement.style.setProperty('--spacing-right-panel', `${rightPanelWidth.value}px`)
  }

  // 初始化时应用
  applyTheme(theme.value)
  applyGlass()
  applyPanelWidths()

  // 监听变化自动持久化
  const all = { theme, fileTreeLeft, agentRight, glassOpacity, glassBlur, fileTreeWidth, rightPanelWidth }
  watch(
    () => ({ ...all, theme: theme.value, fileTreeLeft: fileTreeLeft.value, agentRight: agentRight.value, glassOpacity: glassOpacity.value, glassBlur: glassBlur.value, fileTreeWidth: fileTreeWidth.value, rightPanelWidth: rightPanelWidth.value }),
    (s) => {
      save(s as UserSettings)
      applyTheme(s.theme)
      applyGlass()
      applyPanelWidths()
    },
    { deep: true }
  )

  function resetDefaults() {
    applyTheme(DEFAULTS.theme)
    fileTreeLeft.value = DEFAULTS.fileTreeLeft
    agentRight.value = DEFAULTS.agentRight
    glassOpacity.value = DEFAULTS.glassOpacity
    glassBlur.value = DEFAULTS.glassBlur
    fileTreeWidth.value = DEFAULTS.fileTreeWidth
    rightPanelWidth.value = DEFAULTS.rightPanelWidth
    applyGlass()
    applyPanelWidths()
  }

  return { theme, fileTreeLeft, agentRight, glassOpacity, glassBlur, fileTreeWidth, rightPanelWidth, applyTheme, applyGlass, applyPanelWidths, resetDefaults }
})
