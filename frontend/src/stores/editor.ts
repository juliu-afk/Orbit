import { defineStore } from 'pinia'
import { ref } from 'vue'
import { apiGet } from '@/services/api'

export const useEditorStore = defineStore('editor', () => {
  const currentFile = ref<string|null>(null); const original = ref(''); const modified = ref(''); const language = ref('python'); const loading = ref(false)

  async function openFile(path: string, revA?: string, revB?: string|null) {
    loading.value = true
    try {
      const p = new URLSearchParams({ path }); if (revA) p.set('rev_a', revA); if (revB) p.set('rev_b', revB)
      const d = await apiGet<{diff_text?:string;original?:string;modified?:string;language?:string;content?:string}>(`/api/v1/files/diff?${p.toString()}`)
      original.value = d.original || ''; modified.value = d.modified || d.content || d.diff_text || ''; language.value = d.language || 'python'; currentFile.value = path
    } catch { const p = new URLSearchParams({ path }); const d = await apiGet<{content:string;language:string}>(`/api/v1/files/read?${p.toString()}`); original.value=''; modified.value=d.content; language.value=d.language; currentFile.value=path } finally { loading.value=false }
  }

  return { currentFile, original, modified, language, loading, openFile }
})
