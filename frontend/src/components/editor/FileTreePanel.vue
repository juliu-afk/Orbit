<!-- 文件树面板——自研 Vue 3 递归组件，集成审查状态图标 -->
<template>
  <div class="file-tree-panel">
    <div class="tree-header">
      <span>文件</span>
      <span class="file-count">{{ fileCount }}</span>
    </div>
    <div class="tree-body">
      <FileTreeNode
        v-for="node in treeData"
        :key="node.path"
        :node="node"
        :selected="selectedFile"
        :depth="0"
        @select="$emit('select-file', $event)"
      />
      <el-empty v-if="!treeData.length" description="无文件" :image-size="40" />
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import FileTreeNode from './FileTreeNode.vue'

export interface FileNode {
  name: string
  path: string
  isDir: boolean
  children?: FileNode[]
  reviewStatus?: 'approved' | 'rejected' | 'pending' | null
  coveragePct?: number  // 0-100
}

const props = defineProps<{
  treeData: FileNode[]
  selectedFile: string | null
}>()

defineEmits<{
  (e: 'select-file', path: string): void
}>()

const fileCount = computed(() => {
  function count(nodes: FileNode[]): number {
    let n = 0
    for (const node of nodes) {
      if (!node.isDir) n++
      if (node.children) n += count(node.children)
    }
    return n
  }
  return count(props.treeData)
})
</script>

<style scoped>
.file-tree-panel {
  height: 100%;
  display: flex;
  flex-direction: column;
  background: var(--el-bg-color);
}
.tree-header {
  padding: 8px 12px;
  font-weight: 600;
  font-size: 13px;
  border-bottom: 1px solid var(--el-border-color-light);
  display: flex;
  justify-content: space-between;
}
.file-count {
  color: var(--el-text-color-secondary);
  font-size: 12px;
}
.tree-body {
  flex: 1;
  overflow-y: auto;
  padding: 4px 0;
}
</style>
