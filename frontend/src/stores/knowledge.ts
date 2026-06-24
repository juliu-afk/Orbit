/** Knowledge Store??????????
 *
 * ?????
 */
import { defineStore } from 'pinia'
import { ref } from 'vue'

const KNOWLEDGE_URL = '/api/v1/knowledge'
const COMPLIANCE_URL = '/api/v1/compliance'

export interface KnowledgeConcept {
  domain: string
  concept: string
  definition: string
  formula?: string
  source_level: number
  category?: string
}

export interface ComplianceResult {
  concept: string
  domain: string
  status: string
  violations: string[]
  warnings: string[]
  rules_checked: number
}

export const useKnowledgeStore = defineStore('knowledge', () => {
  const concepts = ref<KnowledgeConcept[]>([])
  const currentConcept = ref<KnowledgeConcept | null>(null)
  const complianceResult = ref<ComplianceResult | null>(null)
  const loading = ref(false)
  const error = ref<string | null>(null)

  /** ?????? */
  async function queryConcept(domain: string, concept: string) {
    loading.value = true
    error.value = null
    try {
      const r = await fetch(`${KNOWLEDGE_URL}?domain=${encodeURIComponent(domain)}&concept=${encodeURIComponent(concept)}`)
      const j = await r.json()
      if (r.ok) {
        currentConcept.value = j
      } else {
        error.value = j.detail || '?????'
        currentConcept.value = null
      }
    } catch (e) {
      error.value = String(e)
    } finally {
      loading.value = false
    }
  }

  /** ???? */
  async function search(query: string) {
    loading.value = true
    try {
      const r = await fetch(`${KNOWLEDGE_URL}/search?q=${encodeURIComponent(query)}`)
      const j = await r.json()
      if (j.code === 0) {
        concepts.value = j.data || []
      }
    } catch (e) {
      console.warn("[store] ????", e)
    } finally {
      loading.value = false
    }
  }

  /** ?????? */
  async function listConcepts(domain: string) {
    loading.value = true
    try {
      const r = await fetch(`${KNOWLEDGE_URL}/concepts?domain=${encodeURIComponent(domain)}`)
      const j = await r.json()
      if (j.code === 0) {
        concepts.value = j.data || []
      }
    } catch (e) {
      console.warn("[store] ????", e)
    } finally {
      loading.value = false
    }
  }

  /** ????? */
  async function validateCompliance(domain: string, concept: string) {
    loading.value = true
    error.value = null
    try {
      const r = await fetch(`${COMPLIANCE_URL}/validate?domain=${encodeURIComponent(domain)}&concept=${encodeURIComponent(concept)}`)
      const j = await r.json()
      complianceResult.value = j
    } catch (e) {
      error.value = String(e)
    } finally {
      loading.value = false
    }
  }

  function reset() {
    concepts.value = []
    currentConcept.value = null
    complianceResult.value = null
    error.value = null
  }

  return {
    concepts, currentConcept, complianceResult, loading, error,
    queryConcept, search, listConcepts, validateCompliance, reset,
  }
})
