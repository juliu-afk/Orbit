<!-- 递归文件树节点——审查状态图标 -->
<template>
  <div class="tree-node" :class="{ selected: selected === node.path, 'is-dir': node.isDir }"
    :style="{ paddingLeft: depth * 12 + 8 + 'px' }" @click.stop="handleClick">
    <span class="file-icon">{{ node.isDir ? (expanded ? '📂' : '📁') : '📄' }}</span>
    <span class="file-name">{{ node.name }}</span>
    <span v-if="!node.isDir" class="status-dot" :class="statusClass" />
  </div>
  <template v-if="node.isDir && expanded && node.children">
    <FileTreeNode v-for="c in node.children" :key="c.path" :node="c" :selected="selected" :depth="depth+1" @select="$emit('select', $event)" />
  </template>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import type { FileNode } from './FileTreePanel.vue'
const props = defineProps<{ node: FileNode; selected: string | null; depth: number }>()
const emit = defineEmits<{ (e: 'select', path: string): void }>()
const expanded = ref(false)
const S: Record<string, string> = { approved: 'status-approved', rejected: 'status-rejected', pending: 'status-pending' }
const statusClass = computed(() => S[props.node.reviewStatus ?? ''] ?? '')
function handleClick() { if (props.node.isDir) expanded.value = !expanded.value; else emit('select', props.node.path) }
</script>

<style scoped>
.tree-node { display: flex; align-items: center; padding: 2px 8px; cursor: pointer; font-size: 13px; gap: 4px; user-select: none; }
.tree-node:hover { background: var(--el-fill-color-light); }
.tree-node.selected { background: var(--el-color-primary-light-9); }
.tree-node.is-dir { font-weight: 500; }
.file-icon { flex-shrink: 0; font-size: 12px; }
.file-name { flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.status-dot { width: 6px; height: 6px; border-radius: 50%; flex-shrink: 0; background: var(--el-text-color-placeholder); }
.status-approved { background: #67c23a; }
.status-rejected { background: #f56c6c; }
.status-pending { background: #e6a23c; }
</style>
