/** Blame Store（PR5）——git blame 逐行作者标注（Agent vs Human）。
 *
 * 对应后端 GET /api/v1/git/blame?file=X，返回裸数组（每元素=一行）。
 */
import { defineStore } from 'pinia'
import { ref } from 'vue'

export interface BlameLine {
  author: string
  time: string
  email?: string
  is_agent?: boolean
  content: string
}

export const useBlameStore = defineStore('blame', () => {
  const lines = ref<BlameLine[]>([])
  const loading = ref(false)
  const currentFile = ref('')

  // WHY 原生 fetch：blame 端点返回裸数组（非 {code,data} 包装），apiGet 会抛错。
  // 加 30s 超时——大文件 blame 可能慢，与后端超时一致。
  async function fetchBlame(file: string) {
    currentFile.value = file
    loading.value = true
    const ctrl = new AbortController()
    const timer = setTimeout(() => ctrl.abort(), 30000)
    try {
      const r = await fetch(`/api/v1/git/blame?file=${encodeURIComponent(file)}`, { signal: ctrl.signal })
      lines.value = r.ok ? await r.json() : []
    } catch {
      lines.value = []
    } finally {
      clearTimeout(timer)
      loading.value = false
    }
  }

  return { lines, loading, currentFile, fetchBlame }
})
