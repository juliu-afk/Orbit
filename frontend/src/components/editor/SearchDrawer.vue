<script setup lang="ts">
import { ref } from 'vue'
import { apiGet } from '@/services/api'
const props = defineProps<{ show: boolean }>()
const emit = defineEmits<{ (e: 'update:show', val: boolean): void; (e: 'open-file', path: string): void }>()
const query = ref('')
const results = ref<Array<{ path: string; line?: number }>>([])
const searching = ref(false)
async function doSearch() { if (!query.value.trim()) return; searching.value = true; try { const d = await apiGet<{ results: typeof results.value }>(`/api/v1/search?q=${encodeURIComponent(query.value)}`); results.value = d.results || [] } catch { results.value = [] } finally { searching.value = false } }
</script>
<template>
<el-drawer :model-value="props.show" title="Search" direction="rtl" size="520px" @update:model-value="emit('update:show', $event as boolean)">
  <div style="font-family:var(--font-mono)">
    <div class="flex gap-2 mb-3">
      <input v-model="query" class="flex-1 px-3 py-1.5 rounded text-xs outline-none" style="background:var(--color-orbit-surface);border:1px solid var(--color-orbit-border);color:var(--color-orbit-text);font-family:var(--font-mono)" placeholder="search..." @keydown.enter="doSearch" />
      <button class="px-3 py-1.5 rounded text-xs cursor-pointer" style="background:var(--color-orbit-accent-dim);border:none;color:var(--color-orbit-text);font-family:var(--font-mono)" @click="doSearch">{{ searching ? '...' : 'go' }}</button>
    </div>
    <div v-for="r in results" :key="r.path" class="px-2 py-1 rounded cursor-pointer flex justify-between text-xs" style="border-bottom:1px solid var(--color-orbit-border-light)" @click="emit('open-file', r.path)">
      <span style="color:var(--color-orbit-info)">{{ r.path }}</span>
      <span v-if="r.line" style="color:var(--color-orbit-text-muted)">:{{ r.line }}</span>
    </div>
  </div>
</el-drawer>
</template>
