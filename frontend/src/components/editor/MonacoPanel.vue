<script setup lang="ts">
// WHY v0.22.1: MonacoPanel 底部加 5 tab——Problems/Outline/Tests/Terminal/Conflicts。
// 替代旧 ReviewView 底部 tab 栏，将代码审查辅助功能内嵌到 Monaco 面板。
import { ref, defineAsyncComponent } from 'vue'
import { useEditorStore } from '@/stores/editor'
import { useShellStore } from '@/stores/shell'
import { useDiagnosticsStore } from '@/stores/diagnostics'
import ProblemPanel from '@/components/editor/ProblemPanel.vue'
import TestPanel from '@/components/editor/TestPanel.vue'
import MergeConflictPanel from '@/components/editor/MergeConflictPanel.vue'

const editor = useEditorStore()
const shell = useShellStore()
const diag = useDiagnosticsStore()

// P1-4 fix: ProblemPanel 点击 → 打开文件 + 激活 Monaco
function onProblemClick(d: { filePath?: string; file?: string; line?: number }) {
  const fp = d.filePath || d.file || ''
  if (fp) { editor.openFile(fp); shell.openFileReview(fp) }
}

// P1-5 fix: TestPanel show-error → 打开失败文件
function onTestError(t: { name?: string; file?: string; error?: string | null }) {
  const fp = t.file || ''
  if (fp) { editor.openFile(fp); shell.openFileReview(fp) }
}

// WHY 懒加载：Monaco 4MB chunk 只在首次打开代码审查时加载
const MonacoDiffEditor = defineAsyncComponent(() => import('@/components/editor/MonacoDiffEditor.vue'))

const activeTab = ref('problems')
</script>

<template>
<div class="monaco-panel flex flex-col h-full">
  <!-- 文件头 -->
  <div class="flex items-center justify-between px-3 py-1.5 shrink-0" style="border-bottom:1px solid var(--color-orbit-border);font-family:var(--font-mono);font-size:11px;color:var(--color-orbit-text-secondary)">
    <span>{{ editor.currentFile || 'untitled' }}</span>
    <button style="background:none;border:none;color:var(--color-orbit-text-muted);cursor:pointer;font-family:var(--font-mono);font-size:14px" @click="shell.closeFileReview()">x</button>
  </div>

  <!-- Monaco 编辑器 -->
  <div class="flex-1 overflow-hidden">
    <Suspense>
      <template #default>
        <MonacoDiffEditor v-if="editor.currentFile" :original="editor.original" :modified="editor.modified" :language="editor.language" height="100%" />
        <div v-else class="flex items-center justify-center h-full text-xs" style="color:var(--color-orbit-text-muted)">select a file</div>
      </template>
      <template #fallback><div class="flex items-center justify-center h-full text-xs" style="color:var(--color-orbit-text-muted)">loading editor...</div></template>
    </Suspense>
  </div>

  <!-- 底部 Tab 面板——v0.22.1：替代旧 ReviewView 底部 200px tab 区域 -->
  <div class="shrink-0" style="height:200px;border-top:1px solid var(--color-orbit-border);overflow:hidden">
    <el-tabs v-model="activeTab" class="monaco-tabs" style="height:100%">
      <el-tab-pane label="Problems" name="problems">
        <ProblemPanel :diagnostics="diag.diagnostics" @click="onProblemClick" />
      </el-tab-pane>
      <el-tab-pane label="Tests" name="tests">
        <TestPanel @show-error="onTestError" />
      </el-tab-pane>
      <el-tab-pane label="Conflicts" name="conflicts">
        <MergeConflictPanel @select-file="(path: string) => { editor.openFile(path); shell.openFileReview(path) }" />
      </el-tab-pane>
    </el-tabs>
  </div>
</div>
</template>

<style scoped>
/* WHY 覆盖 Element Plus tab 样式——终端风格 */
.monaco-tabs :deep(.el-tabs__header) {
  margin: 0;
  padding: 0 12px;
  background: var(--color-orbit-surface);
  border-bottom: 1px solid var(--color-orbit-border);
}
.monaco-tabs :deep(.el-tabs__nav-wrap::after) { display: none; }
.monaco-tabs :deep(.el-tabs__item) {
  font-family: var(--font-mono);
  font-size: 11px;
  color: var(--color-orbit-text-secondary);
  height: 32px;
  line-height: 32px;
}
.monaco-tabs :deep(.el-tabs__item.is-active) {
  color: var(--color-orbit-accent);
}
.monaco-tabs :deep(.el-tabs__content) {
  height: calc(100% - 32px);
  overflow-y: auto;
  padding: 0;
}
</style>
