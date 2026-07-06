<!-- Monaco DiffEditor 封装——Phase 1 审查界面核心组件 -->
<template>
  <div class="monaco-diff-wrapper" :style="{ height }">
    <div ref="containerRef" class="monaco-diff-container" style="flex:1;overflow:hidden;" />
    <div v-if="hunks.length" class="hunk-nav">
      <span class="hunk-label">Hunk {{ currentHunk + 1 }} / {{ hunks.length }}</span>
      <el-button size="small" :disabled="currentHunk <= 0" @click="navigateHunk(-1)">&lt;</el-button>
      <el-button size="small" :disabled="currentHunk >= hunks.length - 1" @click="navigateHunk(1)">&gt;</el-button>
      <el-button size="small" type="success" @click="$emit('approve-hunk', currentHunk)">Approve Hunk</el-button>
      <el-button size="small" type="danger" @click="$emit('reject-hunk', currentHunk)">Reject Hunk</el-button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, watch, onMounted, onBeforeUnmount, shallowRef } from 'vue'
import * as monaco from 'monaco-editor'
import { apiGet } from '@/services/api'

// Monaco CancellationToken 缺少 isCancellationRequested 类型声明
interface CancellableToken extends monaco.CancellationToken {
  isCancellationRequested: boolean
}

const props = withDefaults(defineProps<{
  original: string; modified: string; language?: string; height?: string; readOnly?: boolean
}>(), { language: 'python', height: '600px', readOnly: true })

const emit = defineEmits<{
  (e: 'approve-hunk', hunkIndex: number): void
  (e: 'reject-hunk', hunkIndex: number): void
}>()

const containerRef = ref<HTMLDivElement>()
const diffEditor = shallowRef<monaco.editor.IStandaloneDiffEditor>()
const currentHunk = ref(0)
const hunks = ref<monaco.editor.ILineChange[]>([])
const _hunkTimer = ref<ReturnType<typeof setTimeout>>()  // P1-1
const _oldModel = { o: null as monaco.editor.ITextModel | null, m: null as monaco.editor.ITextModel | null }  // P2-1
const _providerDisposables: monaco.IDisposable[] = []  // P1-1

// 从 Monaco diff 中提取 hunk 列表
function updateHunks() {
  if (!diffEditor.value) { hunks.value = []; return }
  const changes = diffEditor.value.getLineChanges()
  hunks.value = changes || []
  if (currentHunk.value >= hunks.value.length) currentHunk.value = Math.max(0, hunks.value.length - 1)
}

// 导航到上一个/下一个 hunk
function navigateHunk(direction: number) {
  const next = currentHunk.value + direction
  if (next < 0 || next >= hunks.value.length) return
  currentHunk.value = next
  const hunk = hunks.value[next]
  const line = hunk.modifiedStartLineNumber != null && hunk.modifiedStartLineNumber > 0
    ? hunk.modifiedStartLineNumber : hunk.originalStartLineNumber
  if (line > 0) diffEditor.value?.revealPositionInCenter({ lineNumber: line, column: 1 })
}

onMounted(() => {
  if (!containerRef.value) return
  diffEditor.value = monaco.editor.createDiffEditor(containerRef.value, {
    readOnly: props.readOnly, renderSideBySide: true, minimap: { enabled: false },
    scrollBeyondLastLine: false, automaticLayout: true, glyphMargin: true,
    folding: true, lineNumbers: 'on', renderIndicators: true, originalEditable: false,
  })
  updateModel()
  // IDE功能追赶: 注册 Go to Def / References / Hover providers
  registerLanguageProviders()
})

// IDE功能追赶——Monaco Language Providers (Go to Def / References / Hover)
function registerLanguageProviders() {
  const lang = props.language
  _providerDisposables.push(
    // Definition Provider: Ctrl+Click
    monaco.languages.registerDefinitionProvider(lang, {
      provideDefinition: async (model, position, token) => {
        const word = model.getWordAtPosition(position)
        if (!word) return null
        try {
          const data = await apiGet<{ file: string; line: number; column: number }>(
            `/api/v1/codegraph/definition?symbol=${encodeURIComponent(word.word)}`
          )
          if ((token as CancellableToken).isCancellationRequested) return null
          if (data?.file) {
            const col = data.column || 1
            return { uri: monaco.Uri.file(data.file), range: { startLineNumber: data.line || 1, startColumn: col, endLineNumber: data.line || 1, endColumn: col + word.word.length } }
          }
        } catch { /* fail-silent */ }
        return null
      },
    }),
    // Reference Provider: Shift+F12
    monaco.languages.registerReferenceProvider(lang, {
      provideReferences: async (model, position, token) => {
        const word = model.getWordAtPosition(position)
        if (!word) return []
        try {
          const data = await apiGet<{ references: { name: string; file?: string; line?: number }[] }>(
            `/api/v1/codegraph/references?symbol=${encodeURIComponent(word.word)}`
          )
          if ((token as CancellableToken).isCancellationRequested) return []
          return (data?.references || []).map(ref => ({
            uri: monaco.Uri.file(ref.file || ''),
            range: { startLineNumber: ref.line || 1, startColumn: 1, endLineNumber: ref.line || 1, endColumn: 1 },
          }))
        } catch { return [] }
      },
    }),
    // Hover Provider
    monaco.languages.registerHoverProvider(lang, {
      provideHover: async (model, position, token) => {
        const word = model.getWordAtPosition(position)
        if (!word) return null
        try {
          const data = await apiGet<{ info: string }>(
            `/api/v1/codegraph/hover?symbol=${encodeURIComponent(word.word)}`
          )
          if ((token as CancellableToken).isCancellationRequested) return null
          if (data?.info) {
            return { contents: [{ value: data.info, isTrusted: false }] }  // P1-3
          }
        } catch { /* fail-silent */ }
        return null
      },
    }),
  )
}

function updateModel() {
  if (!diffEditor.value) return
  if (_oldModel.o) _oldModel.o.dispose()  // P2-1
  if (_oldModel.m) _oldModel.m.dispose()
  const om = monaco.editor.createModel(props.original, props.language)
  const mm = monaco.editor.createModel(props.modified, props.language)
  _oldModel.o = om; _oldModel.m = mm
  diffEditor.value.setModel({ original: om, modified: mm })
}
watch(() => [props.original, props.modified, props.language], updateModel)
watch(() => props.language, () => registerLanguageProviders())  // P2-1
// 模型变更后重新计算 hunk 列表
watch(() => [props.original, props.modified], () => {
  if (_hunkTimer.value) clearTimeout(_hunkTimer.value)
  _hunkTimer.value = setTimeout(updateHunks, 100)
})
onBeforeUnmount(() => {
  if (_hunkTimer.value) clearTimeout(_hunkTimer.value)
  _providerDisposables.forEach(d => d.dispose())
  _providerDisposables.length = 0
  diffEditor.value?.dispose()
})
</script>

<style scoped>
.monaco-diff-container { border: 1px solid var(--el-border-color-light); border-radius: 4px; }
.monaco-diff-wrapper { display: flex; flex-direction: column; }
.hunk-nav { display: flex; align-items: center; gap: 6px; padding: 4px 8px; border: 1px solid var(--el-border-color-light); border-top: none; border-radius: 0 0 4px 4px; background: var(--el-bg-color); flex-shrink: 0; }
.hunk-label { font-size: 12px; color: var(--el-text-color-secondary); margin-right: auto; }
</style>
