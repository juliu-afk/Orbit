<!-- IDE功能追赶——合并冲突查看器 -->
<template>
  <div class="merge-conflict-panel">
    <div v-if="loading" class="loading-text">加载冲突列表...</div>
    <div v-else-if="conflicts.length === 0" class="empty-text">
      <el-empty description="无合并冲突" :image-size="40" />
    </div>
    <div v-else class="conflict-list">
      <div v-for="(f, i) in conflicts" :key="f" class="conflict-item"
        :class="{ active: i === selected && selected >= 0 }" @click="$emit('select-file', f); selected = i">
        <el-icon><WarningFilled /></el-icon>
        <span class="conflict-path">{{ f }}</span>
      </div>
    </div>
    <div v-if="conflicts.length" class="conflict-actions">
      <el-button size="small" @click="refresh">刷新</el-button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, watch } from 'vue'
import { WarningFilled } from '@element-plus/icons-vue'
import { apiGet } from '@/services/api'

const conflicts = ref<string[]>([])
const loading = ref(false)
const selected = ref(-1)  // -1 = 未选中

async function refresh() {
  loading.value = true
  try {
    // 后端直接返回 string[]，非 {files: string[]}
    const data = await apiGet<string[]>('/api/v1/git/merge-conflicts')
    conflicts.value = Array.isArray(data) ? data : []
  } catch { conflicts.value = [] }
  finally { loading.value = false }
}

onMounted(refresh)
watch(conflicts, () => { selected.value = conflicts.value.length > 0 ? 0 : -1 })
defineExpose({ refresh })
</script>

<style scoped>
.merge-conflict-panel { padding: 4px 0; }
.loading-text, .empty-text { padding: 8px; color: var(--el-text-color-secondary); font-size: 13px; }
.conflict-list { display: flex; flex-direction: column; gap: 2px; }
.conflict-item { display: flex; align-items: center; gap: 6px; padding: 4px 8px; cursor: pointer; border-radius: 4px; font-size: 13px; }
.conflict-item:hover { background: var(--el-fill-color-light); }
.conflict-item.active { background: var(--el-color-primary-light-9); }
.conflict-item .el-icon { color: var(--el-color-warning); flex-shrink: 0; }
.conflict-path { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.conflict-actions { padding: 4px 0; }
</style>
