/** Ops Store——备份/版本/SOP 数据管理。 */
import { defineStore } from 'pinia'
import { ref } from 'vue'

export interface SnapshotItem {
  name: string
  path: string
  size_mb: number
  modified: number
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

export const useOpsStore = defineStore('ops', () => {
  const snapshots = ref<SnapshotItem[]>([])
  const releases = ref<ReleaseEvent[]>([])
  const currentVersion = ref<string>('')
  const sopContent = ref<string>('')
  const loading = ref(false)

  async function fetchSnapshots() {
    try {
      // 占位：后续用专用备份列表端点
      snapshots.value = []
    } catch {
      // 静默
    }
  }

  async function fetchReleases() {
    // 占位：后续用专用版本端点 GET /api/v1/versioning/releases
    releases.value = []
  }

  async function fetchVersion() {
    try {
      // 占位：后续 GET /api/v1/versioning/current
      const r = await fetch('/api/v1/observability/health')
      const j = await r.json()
      currentVersion.value = j.overall || '未知'
    } catch {
      currentVersion.value = '---'
    }
  }

  async function fetchSop() {
    try {
      const r = await fetch('/SOP-灾难恢复手册.md')
      if (r.ok) {
        sopContent.value = await r.text()
      }
    } catch {
      sopContent.value = '# SOP 手册暂不可用'
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
