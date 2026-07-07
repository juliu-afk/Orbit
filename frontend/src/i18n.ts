/** i18n 国际化——UX 长期 #14.
 *
 * 使用 vue-i18n 实现中英双语切换。
 * 默认语言从 localStorage 读取，无记录时用 zh-CN。
 */
import { createI18n } from 'vue-i18n'
import zhCN from './locales/zh-CN.json'
import en from './locales/en.json'

const LOCALE_KEY = 'orbit-locale'

function getSavedLocale(): string {
  try {
    const saved = localStorage.getItem(LOCALE_KEY)
    if (saved && ['zh-CN', 'en'].includes(saved)) return saved
  } catch {
    // localStorage 不可用
  }
  return 'zh-CN'
}

export const i18n = createI18n({
  legacy: false, // Composition API 模式
  locale: getSavedLocale(),
  fallbackLocale: 'zh-CN',
  messages: { 'zh-CN': zhCN, en },
})

/** 切换语言并持久化。*/
export function setLocale(locale: 'zh-CN' | 'en'): void {
  i18n.global.locale.value = locale
  try {
    localStorage.setItem(LOCALE_KEY, locale)
  } catch {
    // localStorage 不可用
  }
}

/** 获取当前语言。*/
export function getCurrentLocale(): string {
  return i18n.global.locale.value
}
