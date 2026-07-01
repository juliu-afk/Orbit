<script setup lang="ts">
// WHY 新建：搜索面板浮层——文件/内容搜索（Ctrl+K 快捷键）。
// 保留旧 SearchPanel.vue 的数据获取逻辑，去掉 Element Plus 依赖。
import { ref } from 'vue'
import { apiGet } from '@/services/api'

defineProps<{
  show: boolean
}>()

const emit = defineEmits<{
  (e: 'update:show', val: boolean): void
  (e: 'open-file', path: string): void
}>()

const query = ref('')
const results = ref<Array<{ path: string; line?: number; content?: string }>>([])
const searching = ref(false)

async function doSearch() {
  if (!query.value.trim()) return
  searching.value = true
  try {
    const data = await apiGet<{ results: typeof results.value }>(
      `/api/v1/search?q=${encodeURIComponent(query.value)}`
    )
    results.value = data.results || []
  } catch {
    results.value = []
  } finally {
    searching.value = false
  }
}

function onSelectResult(path: string) {
  emit('open-file', path)
  emit('update:show', false)
}
</script>

<template>
  <el-drawer
    :model-value="show"
    title="搜索"
    direction="rtl"
    size="520px"
    @update:model-value="emit('update:show', $event as boolean)"
  >
    <div class="search-content" style="font-family: var(--font-mono);">
      <!-- 搜索框 -->
      <div class="flex gap-2 mb-3">
        <input
          v-model="query"
          class="search-input flex-1 px-3 py-1.5 rounded text-xs outline-none"
          style="
            background: var(--color-orbit-surface);
            border: 1px solid var(--color-orbit-border);
            color: var(--color-orbit-text);
            font-family: var(--font-mono);
          "
          placeholder="搜索文件或内容..."
          @keydown.enter="doSearch"
        />
        <button
          class="search-btn px-3 py-1.5 rounded text-xs cursor-pointer"
          style="
            background: var(--color-orbit-accent-dim);
            border: none;
            color: var(--color-orbit-text);
            font-family: var(--font-mono);
          "
          @click="doSearch"
        >
          {{ searching ? '...' : '搜索' }}
        </button>
      </div>

      <!-- 结果列表 -->
      <div
        v-if="results.length === 0 && !searching"
        class="text-xs"
        style="color: var(--color-orbit-text-muted);"
      >
        输入关键词搜索文件
      </div>

      <div
        v-for="r in results"
        :key="r.path"
        class="result-item px-2 py-1 rounded cursor-pointer flex justify-between text-xs"
        style="border-bottom: 1px solid var(--color-orbit-border-light);"
        @click="onSelectResult(r.path)"
      >
        <span style="color: var(--color-orbit-info);">{{ r.path }}</span>
        <span v-if="r.line" style="color: var(--color-orbit-text-muted);">:{{ r.line }}</span>
      </div>
    </div>
  </el-drawer>
</template>

<style scoped>
.search-input::placeholder {
  color: var(--color-orbit-text-muted);
}
.search-input:focus {
  border-color: var(--color-orbit-accent);
}
.result-item:hover {
  background: var(--color-orbit-surface-hover);
}
</style>
