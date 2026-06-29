<<<<<<< HEAD
/** 诊断状态——L4 mypy 输出 */
=======
>>>>>>> 1cdddeacb9fe2b301c27aaa7e82c7080c6549313
import { defineStore } from 'pinia'
import { ref } from 'vue'
import { apiGet } from '@/services/api'

<<<<<<< HEAD
export interface Diagnostic {
  filePath: string
  line: number
  column: number
  severity: 'error' | 'warning' | 'info'
  message: string
  ruleId: string | null
}

export const useDiagnosticsStore = defineStore('diagnostics', () => {
  const diagnostics = ref<Diagnostic[]>([])
  const loading = ref(false)

  async function fetchDiagnostics(taskId: string, file?: string) {
    loading.value = true
    try {
      const params = new URLSearchParams({ task_id: taskId })
      if (file) params.set('file', file)
      const data = await apiGet<{ diagnostics: Record<string, { line: number; column: number; severity: string; message: string; rule_id?: string | null }[]> }>(
        `/api/v1/lsp/diagnostics?${params.toString()}`
      )
      const all: Diagnostic[] = []
      for (const [fp, diags] of Object.entries(data.diagnostics || {})) {
        for (const d of diags) {
          all.push({
            filePath: fp,
            line: d.line,
            column: d.column,
            severity: d.severity as Diagnostic['severity'],
            message: d.message,
            ruleId: d.rule_id ?? null,
          })
        }
      }
      diagnostics.value = all
    } finally {
      loading.value = false
    }
=======
export interface Diagnostic { filePath: string; line: number; column: number; severity: 'error'|'warning'|'info'; message: string; ruleId: string|null }

export const useDiagnosticsStore = defineStore('diagnostics', () => {
  const diagnostics = ref<Diagnostic[]>([]); const loading = ref(false)

  async function fetchDiagnostics(taskId: string, file?: string) {
    loading.value = true
    try { const p = new URLSearchParams({ task_id: taskId }); if (file) p.set('file', file); const d = await apiGet<{diagnostics:Record<string,{line:number;column:number;severity:string;message:string;rule_id?:string|null}[]>}>(`/api/v1/lsp/diagnostics?${p.toString()}`); const all: Diagnostic[] = []; for (const [fp, diags] of Object.entries(d.diagnostics||{})) for (const x of diags) all.push({filePath:fp,line:x.line,column:x.column,severity:x.severity as Diagnostic['severity'],message:x.message,ruleId:x.rule_id??null}); diagnostics.value=all } finally { loading.value=false }
>>>>>>> 1cdddeacb9fe2b301c27aaa7e82c7080c6549313
  }

  return { diagnostics, loading, fetchDiagnostics }
})
