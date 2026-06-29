/** 编辑器状态——当前文件、diff 内容、语言 */
import { defineStore } from 'pinia'
import { ref } from 'vue'
import { apiGet } from '@/services/api'

export const useEditorStore = defineStore('editor', () => {
  const currentFile = ref<string | null>(null)
  const original = ref('')
  const modified = ref('')
  const language = ref('python')
  const loading = ref(false)

  async function openFile(path: string, revA?: string, revB?: string | null) {
    loading.value = true
    try {
      const params = new URLSearchParams({ path })
      if (revA) params.set('rev_a', revA)
      if (revB) params.set('rev_b', revB)
      const data = await apiGet<{ diff_text?: string; original?: string; modified?: string; language?: string; content?: string; error?: string }>(
        `/api/v1/files/diff?${params.toString()}`
      )
      if (data.diff_text !== undefined) {
        // unified diff——Monaco 需要分离 original/modified
        original.value = ''
        modified.value = data.diff_text
      } else {
        original.value = data.original || ''
        modified.value = data.modified || data.content || ''
      }
      language.value = data.language || 'python'
      currentFile.value = path
    } catch {
      // 文件无 diff——读取文件内容作为 modified
      const params = new URLSearchParams({ path })
      const data = await apiGet<{ content: string; language: string }>(
        `/api/v1/files/read?${params.toString()}`
      )
      original.value = ''
      modified.value = data.content
      language.value = data.language
      currentFile.value = path
    } finally {
      loading.value = false
    }
  }

  return { currentFile, original, modified, language, loading, openFile }
})
