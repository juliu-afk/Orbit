<!-- 代码输出展示面板——任务完成时在抽屉中弹出 -->
<template>
  <div class="code-diff-panel">
    <div class="code-diff-panel__body">
      <pre class="code-diff-panel__pre"><code>{{ code }}</code></pre>
    </div>
  </div>
</template>

<script setup lang="ts">
defineProps<{
  code: string
}>()
</script>

<style scoped>
.code-diff-panel {
  height: 100%;
  display: flex;
  flex-direction: column;
  background: #0a0a14;
}
.code-diff-panel__body {
  flex: 1;
  overflow: auto;
  padding: 16px;
}
.code-diff-panel__pre {
  margin: 0;
  padding: 12px;
  background: #0f0f1a;
  border: 1px solid #2a2a4a;
  border-radius: 4px;
  font-family: 'Cascadia Code', 'Fira Code', 'Consolas', monospace;
  font-size: 12px;
  line-height: 1.6;
  color: #e0e0e0;
  white-space: pre-wrap;
  word-break: break-all;
  overflow-x: auto;
  min-height: 200px;
}
</style>
