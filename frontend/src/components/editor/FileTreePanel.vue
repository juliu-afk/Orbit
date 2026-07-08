<!-- 文件树面板——Vue 3 递归组件，集成审查状态图标 + 项目选择器 -->
<template>
  <div class="file-tree-panel">
    <FileTreeProjectBar
      :current-path="currentProjectPath"
      @change-project="$emit('change-project', $event)"
      @create-project="$emit('create-project', $event)"
    />
    <div class="tree-header"><span>Files</span><span class="file-count">{{ fileCount }}</span></div>
    <div class="tree-body">
      <SkeletonPanel v-if="loading" :lines="8" height="auto" />
      <FileTreeNode v-else v-for="n in treeData" :key="n.path" :node="n" :selected="selectedFile" :depth="0" @select="$emit('select-file', $event)" />
      <el-empty v-if="!loading && !treeData.length" description="No files" :image-size="40" />
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import FileTreeNode from './FileTreeNode.vue'
import FileTreeProjectBar from './FileTreeProjectBar.vue'
import SkeletonPanel from '@/components/common/SkeletonPanel.vue'  // UX-6

export interface FileNode {
  name: string; path: string; isDir: boolean; children?: FileNode[]
  reviewStatus?: 'approved' | 'rejected' | 'pending' | null; coveragePct?: number
}

const props = defineProps<{
  treeData: FileNode[]; selectedFile: string | null; loading?: boolean
  currentProjectPath: string
}>()
defineEmits<{
  (e: 'select-file', path: string): void
  (e: 'change-project', path: string): void
  (e: 'create-project', projectName: string): void
}>()

const fileCount = computed(() => {
  function c(nodes: FileNode[]): number { let n = 0; for (const x of nodes) { if (!x.isDir) n++; if (x.children) n += c(x.children) } return n }
  return c(props.treeData || [])
})
</script>

<style scoped>
.file-tree-panel { height: 100%; display: flex; flex-direction: column; background: transparent; }
.tree-header { padding: 8px 12px; font-weight: 600; font-size: 13px; border-bottom: 1px solid var(--color-orbit-border); display: flex; justify-content: space-between; color: var(--color-orbit-text); }
.file-count { color: var(--color-orbit-text-secondary); font-size: 12px; }
.tree-body { flex: 1; overflow-y: auto; padding: 4px 0; }
</style>
