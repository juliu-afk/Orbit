<!-- 轻量编辑器——Monaco 可写模式+代码片段 (Phase 2.4) -->
<template>
  <div class="light-editor">
    <div class="editor-toolbar">
      <el-button size="small" :type="readOnly ? 'default' : 'primary'" @click="readOnly = !readOnly">
        {{ readOnly ? 'Edit' : 'Lock' }}
      </el-button>
      <el-button size="small" @click="save" :loading="saving" :disabled="readOnly">Save</el-button>
      <el-select size="small" v-model="language" style="width:120px" @change="loadSnippets">
        <el-option v-for="l in LANGUAGES" :key="l" :label="l" :value="l" />
      </el-select>
      <span v-if="saved" class="saved-msg">Saved</span>
    </div>
    <div ref="editorRef" class="editor-container" />
    <div v-if="snippets.length" class="snippet-bar">
      <span class="snippet-label">Snippets:</span>
      <el-button v-for="s in snippets" :key="s.label" size="small" text @click="insert(s.body)">{{ s.label }}</el-button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onBeforeUnmount, shallowRef } from 'vue'
import * as monaco from 'monaco-editor'
import { apiPost } from '@/services/api'

const props = defineProps<{ file: string; initialContent: string }>()
const emit = defineEmits<{ (e: 'saved', content: string): void }>()

const LANGUAGES = ['python','typescript','javascript','sql','yaml','json','markdown']
const SNIPPETS: Record<string, { label: string; body: string }[]> = {
  python: [
    { label: 'def', body: 'def function_name():\n    ' },
    { label: 'class', body: 'class ClassName:\n    def __init__(self):\n        ' },
    { label: 'test', body: 'def test_():\n    """Test ."""\n    assert True\n' },
  ],
  typescript: [
    { label: 'comp', body: 'export const Component = () => {\n  return <div></div>\n}' },
    { label: 'store', body: 'export const useStore = defineStore("name", () => {\n  const data = ref()\n  return { data }\n})' },
  ],
}

const editorRef = ref<HTMLDivElement>()
const editor = shallowRef<monaco.editor.IStandaloneCodeEditor>()
const readOnly = ref(true)
const saving = ref(false)
const saved = ref(false)
const language = ref('python')
const snippets = ref<{ label: string; body: string }[]>([])

function loadSnippets() { snippets.value = SNIPPETS[language.value] || [] }

onMounted(() => {
  if (!editorRef.value) return
  loadSnippets()
  editor.value = monaco.editor.create(editorRef.value, {
    value: props.initialContent, language: language.value,
    readOnly: readOnly.value, minimap: { enabled: false },
    automaticLayout: true, fontSize: 13, lineNumbers: 'on',
  })
})

function insert(body: string) {
  if (!editor.value) return
  const pos = editor.value.getPosition()
  if (!pos) return
  editor.value.executeEdits('snippet', [{ range: new monaco.Range(pos.lineNumber, pos.column, pos.lineNumber, pos.column), text: body }])
}
async function save() {
  if (!editor.value) return
  saving.value = true
  try {
    const content = editor.value.getValue()
    await apiPost('/api/v1/files/write', { path: props.file, content })
    saved.value = true; emit('saved', content)
    setTimeout(() => saved.value = false, 2000)
  } catch {} finally { saving.value = false }
}
onBeforeUnmount(() => editor.value?.dispose())
</script>

<style scoped>
.light-editor { height: 100%; display: flex; flex-direction: column; }
.editor-toolbar { display: flex; align-items: center; gap: 8px; padding: 4px 8px; background: var(--el-bg-color); border-bottom: 1px solid var(--el-border-color-light); }
.editor-container { flex: 1; }
.saved-msg { color: #67c23a; font-size: 12px; }
.snippet-bar { display: flex; align-items: center; gap: 4px; padding: 4px 8px; border-top: 1px solid var(--el-border-color-light); background: var(--el-fill-color-lighter); }
.snippet-label { font-size: 12px; color: var(--el-text-color-secondary); }
</style>
