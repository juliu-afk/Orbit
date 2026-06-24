/** Ops Store????/??/SOP ???????? API?? */
import { defineStore } from 'pinia'
import { ref } from 'vue'

export interface SnapshotItem {
  snapshot_id: string
  path: string
  size_bytes: number
  integrity_hash: string
  created_at: number
  db_type: string
  verified: boolean
}

export interface ReleaseEvent {
  event_type: string
  version: string
  previous_version: string
  trigger: string
  timestamp: number
  success: boolean
}

export interface VersionInfo {
  version: string
  installed_at: number
  description: string
}

const BACKUP_URL = '/api/v1/backup/snapshots'
const VERSIONING_URL = '/api/v1/versioning'

export const useOpsStore = defineStore('ops', () => {
  const snapshots = ref<SnapshotItem[]>([])
  const releases = ref<ReleaseEvent[]>([])
  const currentVersion = ref<string>('')
  const sopContent = ref<string>('')
  const loading = ref(false)

  async function fetchSnapshots() {
    try {
      const r = await fetch(BACKUP_URL)
      const j = await r.json()
      if (j.code === 0) {
        snapshots.value = j.data as SnapshotItem[]
      }
    } catch {
      // ??
    }
  }

  async function fetchReleases() {
    try {
      const r = await fetch(`${VERSIONING_URL}/releases`)
      const j = await r.json()
      if (j.code === 0) {
        releases.value = j.data as ReleaseEvent[]
      }
    } catch {
      // ??
    }
  }

  async function fetchVersion() {
    try {
      const r = await fetch(`${VERSIONING_URL}/current`)
      const j = await r.json()
      if (j.code === 0) {
        currentVersion.value = j.data.version || '??'
      }
    } catch {
      currentVersion.value = '---'
    }
  }

  async function fetchSop() {
    try {
      const r = await fetch('/SOP-??????.md')
      if (r.ok) {
        sopContent.value = await r.text()
      }
    } catch {
      sopContent.value = '# SOP ??????'
    }
  }

  async function fetchAll() {
    loading.value = true
    await Promise.all([fetchSnapshots(), fetchReleases(), fetchVersion(), fetchSop()])
    loading.value = false
  }

  function reset() {
    snapshots.value = []
    releases.value = []
    currentVersion.value = ''
  }

  return { snapshots, releases, currentVersion, sopContent, loading, fetchAll, reset }
})
