<script setup lang="ts">
import { defineAsyncComponent } from 'vue'
import { useEditorStore } from '@/stores/editor'
import { useShellStore } from '@/stores/shell'
const editor = useEditorStore()
const shell = useShellStore()
const MonacoDiffEditor = defineAsyncComponent(() => import('@/components/editor/MonacoDiffEditor.vue'))
</script>
<template>
<div class="monaco-panel flex flex-col h-full">
  <div class="flex items-center justify-between px-3 py-1.5 shrink-0" style="border-bottom:1px solid var(--color-orbit-border);font-family:var(--font-mono);font-size:11px;color:var(--color-orbit-text-secondary)">
    <span>{{ editor.currentFile || 'untitled' }}</span>
    <button style="background:none;border:none;color:var(--color-orbit-text-muted);cursor:pointer;font-family:var(--font-mono);font-size:14px" @click="shell.closeFileReview()">x</button>
  </div>
  <div class="flex-1 overflow-hidden">
    <Suspense>
      <template #default>
        <MonacoDiffEditor v-if="editor.currentFile" :original="editor.original" :modified="editor.modified" :language="editor.language" height="100%" />
        <div v-else class="flex items-center justify-center h-full text-xs" style="color:var(--color-orbit-text-muted)">select a file</div>
      </template>
      <template #fallback><div class="flex items-center justify-center h-full text-xs" style="color:var(--color-orbit-text-muted)">loading editor...</div></template>
    </Suspense>
  </div>
</div>
</template>
