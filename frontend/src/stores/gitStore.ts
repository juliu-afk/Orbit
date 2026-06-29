<<<<<<< HEAD
/** Git 状态——GPG keys、commit */
=======
>>>>>>> 1cdddeacb9fe2b301c27aaa7e82c7080c6549313
import { defineStore } from 'pinia'
import { ref } from 'vue'
import { apiGet, apiPost } from '@/services/api'

<<<<<<< HEAD
export interface GpgKey {
  id: string
  name: string
  email: string
  fingerprint: string
}

export const useGitStore = defineStore('git', () => {
  const gpgKeys = ref<GpgKey[]>([])
  const keysLoading = ref(false)
  const committing = ref(false)

  async function fetchGpgKeys() {
    keysLoading.value = true
    try {
      const data = await apiGet<GpgKey[]>('/api/v1/git/gpg-keys')
      gpgKeys.value = data
    } finally {
      keysLoading.value = false
    }
  }

  async function commit(message: string, files: string[], sign: boolean, gpgKeyId?: string) {
    committing.value = true
    try {
      const data = await apiPost<{ commit_hash: string; verified: boolean }>(
        '/api/v1/git/commit',
        { message, files, sign, gpg_key_id: gpgKeyId || null }
      )
      return data
    } finally {
      committing.value = false
    }
  }
=======
export interface GpgKey { id: string; name: string; email: string; fingerprint: string }

export const useGitStore = defineStore('git', () => {
  const gpgKeys = ref<GpgKey[]>([]); const keysLoading = ref(false); const committing = ref(false)

  async function fetchGpgKeys() { keysLoading.value = true; try { const d = await apiGet<GpgKey[]>('/api/v1/git/gpg-keys'); gpgKeys.value = d } finally { keysLoading.value = false } }
  async function commit(message: string, files: string[], sign: boolean, gpgKeyId?: string) { committing.value = true; try { const d = await apiPost<{commit_hash:string;verified:boolean}>('/api/v1/git/commit',{message,files,sign,gpg_key_id:gpgKeyId||null}); return d } finally { committing.value = false } }
>>>>>>> 1cdddeacb9fe2b301c27aaa7e82c7080c6549313

  return { gpgKeys, keysLoading, committing, fetchGpgKeys, commit }
})
