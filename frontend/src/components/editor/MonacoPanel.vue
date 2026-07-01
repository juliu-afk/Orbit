<script setup lang="ts">
// WHY 新建：包装 MonacoDiffEditor——异步懒加载 + 文件头信息 + 关闭按钮。
// Monaco 4MB chunk 只在首次打开代码审查时加载。
import { defineAsyncComponent } from 'vue'
import { useEditorStore } from '@/stores/editor'
import { useShellStore } from '@/stores/shell'

const editor = useEditorStore()
const shell = useShellStore()

// WHY defineAsyncComponent：Monaco editor 4MB chunk 懒加载，首屏不阻塞
const MonacoDiffEditor = defineAsyncComponent(
  () => import('@/components/editor/MonacoDiffEditor.vue')
)

function onClose() {
  shell.closeFileReview()
}
</script>

<template>
  <div class="monaco-panel flex flex-col h-full">
    <!-- 文件头 -->
    <div
      class="monaco-header flex items-center justify-between px-3 py-1.5 shrink-0"
      style="
        border-bottom: 1px solid var(--color-orbit-border);
        font-family: var(--font-mono);
        font-size: 11px;
        color: var(--color-orbit-text-secondary);
      "
    >
      <span class="flex items-center gap-2">
        <span style="color: var(--color-orbit-accent);">📄</span>
        <span>{{ editor.currentFile || 'untitled' }}</span>
        <span style="color: var(--color-orbit-text-muted);">{{ editor.language }}</span>
      </span>
      <button
        class="close-btn cursor-pointer"
        style="
          background: none;
          border: none;
          color: var(--color-orbit-text-muted);
          font-family: var(--font-mono);
          font-size: 14px;
        "
        @click="onClose"
        title="Close (Esc)"
      >
        ✕
      </button>
    </div>

    <!-- Monaco 编辑器 -->
    <div class="flex-1 overflow-hidden">
      <Suspense>
        <template #default>
          <MonacoDiffEditor
            v-if="editor.currentFile"
            :original="editor.original"
            :modified="editor.modified"
            :language="editor.language"
            height="100%"
          />
          <div
            v-else
            class="flex items-center justify-center h-full text-xs"
            style="color: var(--color-orbit-text-muted);"
          >
            选择文件以查看对比
          </div>
        </template>
        <template #fallback>
          <div
            class="flex items-center justify-center h-full text-xs"
            style="color: var(--color-orbit-text-muted);"
          >
            加载编辑器...
          </div>
        </template>
      </Suspense>
    </div>
  </div>
</template>

<style scoped>
.close-btn:hover {
  color: var(--color-orbit-error);
}
</style>
