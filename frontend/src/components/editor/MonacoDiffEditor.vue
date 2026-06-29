<!-- Monaco DiffEditor 封装——Phase 1 审查界面核心组件 -->
<template>
  <div ref="containerRef" class="monaco-diff-container" :style="{ height }" />
</template>

<script setup lang="ts">
import { ref, watch, onMounted, onBeforeUnmount, shallowRef } from 'vue'
import * as monaco from 'monaco-editor'

const props = withDefaults(defineProps<{
  original: string
  modified: string
  language?: string
  height?: string
  readOnly?: boolean
}>(), {
  language: 'python',
  height: '600px',
  readOnly: true,
})

const emit = defineEmits<{
  (e: 'hunkApprove', payload: { file: string; hunk: number }): void
  (e: 'hunkReject', payload: { file: string; hunk: number }): void
}>()

const containerRef = ref<HTMLDivElement>()
const diffEditor = shallowRef<monaco.editor.IStandaloneDiffEditor>()

onMounted(() => {
  if (!containerRef.value) return

  diffEditor.value = monaco.editor.createDiffEditor(containerRef.value, {
    readOnly: props.readOnly,
    renderSideBySide: true,
    minimap: { enabled: false },
    scrollBeyondLastLine: false,
    automaticLayout: true,
    glyphMargin: true,  // 审批按钮载体
    folding: true,
    lineNumbers: 'on',
    renderIndicators: true,
    originalEditable: false,
  })

  updateModel()
})

function updateModel() {
  if (!diffEditor.value) return
  const originalModel = monaco.editor.createModel(props.original, props.language)
  const modifiedModel = monaco.editor.createModel(props.modified, props.language)
  diffEditor.value.setModel({ original: originalModel, modified: modifiedModel })
}

watch(() => [props.original, props.modified, props.language], () => {
  updateModel()
})

onBeforeUnmount(() => {
  diffEditor.value?.dispose()
})
</script>

<style scoped>
.monaco-diff-container {
  border: 1px solid var(--el-border-color-light);
  border-radius: 4px;
  overflow: hidden;
}
</style>
