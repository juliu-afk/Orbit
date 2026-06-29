/** Git 状态——GPG keys、commit */
import { defineStore } from 'pinia'
import { ref } from 'vue'
import { apiGet, apiPost } from '@/services/api'

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

  return { gpgKeys, keysLoading, committing, fetchGpgKeys, commit }
})
