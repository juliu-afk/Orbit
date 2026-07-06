<!-- 全局搜索面板——Ctrl+P 文件名 / Ctrl+Shift+F 内容 -->
<template>
  <el-dialog v-model="show" title="Search" width="600px" :show-close="true" @closed="emit('close')">
    <el-input v-model="query" placeholder="Search files or content..." prefix-icon="Search" @keyup.enter="doSearch" @keyup.escape="show = false" autofocus :loading="loading" />
    <el-radio-group v-model="searchType" size="small" style="margin-top:8px">
      <el-radio-button value="file">文件名</el-radio-button>
      <el-radio-button value="content">内容</el-radio-button>
    </el-radio-group>
    <div v-if="loading" class="search-loading">Searching...</div>
    <div v-if="results.length" class="search-results">
      <div v-for="(r, i) in results" :key="r.file + ':' + r.line + ':' + i" class="search-result" @click="emit('select', r)">
        <span class="search-file">{{ r.file.split('/').pop() }}</span>
        <span class="search-path">{{ r.file }}</span>
        <span v-if="r.line" class="search-line">:{{ r.line }}</span>
        <span v-if="r.context" class="search-context">{{ r.context.slice(0, 80) }}</span>
      </div>
    </div>
    <div v-else-if="queried && !loading" class="no-results">No results</div>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref, onBeforeUnmount } from 'vue'
import { apiGet } from '@/services/api'
interface SearchResult { file: string; line: number | null; context: string | null }

const emit = defineEmits<{ (e: 'close'): void; (e: 'select', r: SearchResult): void }>()
const show = ref(true)
const query = ref('')
const searchType = ref('file')
const results = ref<SearchResult[]>([])
const queried = ref(false)
const loading = ref(false)
let aborter: AbortController | null = null  // P2: unmount guard

onBeforeUnmount(() => { aborter?.abort() })

async function doSearch() {
  if (query.value.length < 2) return
  loading.value = true; queried.value = true
  aborter?.abort(); aborter = new AbortController()
  try {
    const p = new URLSearchParams({ q: query.value, search_type: searchType.value, max_results: '50' })
    const data = await apiGet<SearchResult[]>(`/api/v1/search?${p.toString()}`)
    if (!aborter.signal.aborted) results.value = data
  } catch (e: unknown) {
    if (e instanceof DOMException && e.name === 'AbortError') return
    if (import.meta.env.DEV) console.error('Search failed:', e)
    results.value = []
  } finally {
    if (!aborter.signal.aborted) loading.value = false
  }
}
</script>

<style scoped>
.search-results { max-height: 400px; overflow-y: auto; margin-top: 8px; }
.search-result { display: flex; align-items: center; gap: 6px; padding: 4px 8px; cursor: pointer; font-size: 13px; }
.search-result:hover { background: var(--el-fill-color-light); }
.search-file { font-weight: 600; flex-shrink: 0; }
.search-path { color: var(--el-text-color-secondary); font-size: 12px; flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.search-line { color: var(--el-color-primary); font-size: 12px; }
.search-context { color: var(--el-text-color-placeholder); font-size: 12px; }
.no-results { padding: 12px; color: var(--el-text-color-secondary); text-align: center; }
.search-loading { padding: 12px; text-align: center; color: var(--el-color-primary); }
</style>
