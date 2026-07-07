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

  async function openFile(path: string, revA?: string, revB?: string | null, dir?: string) {
    loading.value = true
    try {
      const params = new URLSearchParams({ path })
      if (dir) params.set('dir', dir)
      if (revA) params.set('rev_a', revA)
      if (revB) params.set('rev_b', revB)
      const data = await apiGet<{ diff_text?: string; original?: string; modified?: string; language?: string; content?: string; error?: string }>(
        `/api/v1/files/diff?${params.toString()}`
      )
      // WHY diff_text 为空串时说明文件无变更，应回退读取文件原文
      if (data.diff_text) {
        // unified diff——Monaco 需要分离 original/modified
        original.value = ''
        modified.value = data.diff_text
      } else if (data.original || data.modified || data.content) {
        original.value = data.original || ''
        modified.value = data.modified || data.content || ''
      } else {
        // diff 无内容——读取文件原文
        const rparams = new URLSearchParams({ path })
        if (dir) rparams.set('dir', dir)
        const rdata = await apiGet<{ content: string; language: string }>(
          `/api/v1/files/read?${rparams.toString()}`
        )
        original.value = ''
        modified.value = rdata.content
        language.value = rdata.language
        currentFile.value = path
        return
      }
      language.value = data.language || 'python'
      currentFile.value = path
    } catch {
      // API 异常——兜底读取文件内容
      const rparams = new URLSearchParams({ path })
      if (dir) rparams.set('dir', dir)
      try {
        const rdata = await apiGet<{ content: string; language: string }>(
          `/api/v1/files/read?${rparams.toString()}`
        )
        original.value = ''
        modified.value = rdata.content
        language.value = rdata.language
        currentFile.value = path
      } catch {
        modified.value = '// Failed to load file'
        currentFile.value = path
      }
    } finally {
      loading.value = false
    }
  }

  // WHY 聊天代码块直接编辑: 无文件路径，将代码内容作为临时视图打开
  function openCode(code: string, lang: string = 'python') {
    original.value = ''
    modified.value = code
    language.value = lang
    currentFile.value = `[code].${lang}`
  }

  return { currentFile, original, modified, language, loading, openFile, openCode }
})
