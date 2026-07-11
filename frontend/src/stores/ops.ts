/** Ops Store - backup/version/SOP management. */
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
    }
  }

  async function fetchVersion() {
    try {
      const r = await fetch(`${VERSIONING_URL}/current`)
      const j = await r.json()
      if (j.code === 0) {
        currentVersion.value = j.data.version || 'unknown'
      }
    } catch {
      currentVersion.value = '---'
    }
  }

  async function fetchSop() {
    try {
      const r = await fetch('/SOP-disaster-recovery.md')
      if (r.ok) {
        sopContent.value = await r.text()
      }
    } catch {
      sopContent.value = '# SOP unavailable'
    }
  }

  async function fetchAll() {
    loading.value = true
    await Promise.all([fetchSnapshots(), fetchReleases(), fetchVersion(), fetchSop()])
    loading.value = false
  }

  // PR9: 从快照恢复。后端 Restorer 已内置护栏——覆盖前自动备份 .backup，校验失败自动回滚。
  // 前端仍需显式 target + 二次确认(在组件层)。失败抛错由调用方捕获。
  async function restoreSnapshot(snapshotId: string, targetPath: string): Promise<void> {
    const r = await fetch('/api/v1/backup/restore', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ snapshot_id: snapshotId, target_path: targetPath }),
    })
    const j = await r.json().catch(() => ({}))
    if (!r.ok || j.code !== 0) {
      throw new Error(j.detail || j.message || `恢复失败 (HTTP ${r.status})`)
    }
    await fetchSnapshots()
  }

  function reset() {
    snapshots.value = []
    releases.value = []
    currentVersion.value = ''
  }

  return { snapshots, releases, currentVersion, sopContent, loading, fetchAll, restoreSnapshot, reset }
})
