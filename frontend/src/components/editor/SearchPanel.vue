<!-- 全局搜索面板——Ctrl+P 文件名 / Ctrl+Shift+F 内容 -->
<template>
  <el-dialog v-model="visible" title="Search" width="600px" :show-close="true" @closed="$emit('close')">
    <el-input v-model="query" placeholder="Search files or content..." prefix-icon="Search" @keyup.enter="doSearch" @keyup.escape="visible = false" autofocus />
    <el-radio-group v-model="searchType" size="small" style="margin-top:8px">
      <el-radio-button value="file">文件名</el-radio-button>
      <el-radio-button value="content">内容</el-radio-button>
    </el-radio-group>
    <div v-if="results.length" class="search-results">
      <div v-for="r in results" :key="r.file + r.line" class="search-result" @click="$emit('select', r)">
        <span class="search-file">{{ r.file.split('/').pop() }}</span>
        <span class="search-path">{{ r.file }}</span>
        <span v-if="r.line" class="search-line">:{{ r.line }}</span>
        <span v-if="r.context" class="search-context">{{ r.context.slice(0, 80) }}</span>
      </div>
    </div>
    <div v-else-if="queried" class="no-results">No results</div>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { apiGet } from '@/services/api'
interface SearchResult { file: string; line: number | null; context: string | null }

const visible = ref(true)
const query = ref('')
const searchType = ref('file')
const results = ref<SearchResult[]>([])
const queried = ref(false)

const emit = defineEmits<{ (e: 'close'): void; (e: 'select', r: SearchResult): void }>()

async function doSearch() {
  if (query.value.length < 2) return
  queried.value = true
  try {
    const p = new URLSearchParams({ q: query.value, type: searchType.value, max: '50' })
    const data = await apiGet<SearchResult[]>(`/api/v1/search?${p.toString()}`)
    results.value = data
  } catch { results.value = [] }
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
</style>
