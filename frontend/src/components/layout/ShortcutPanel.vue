<script setup lang="ts">
const props = defineProps<{ show: boolean }>()
const emit = defineEmits<{ (e: 'update:show', v: boolean): void }>()
const shortcuts = [
  { key: '⌘B / Ctrl+B', action: 'Toggle file tree' },
  { key: 'Esc', action: 'Close panel / drawer' },
  { key: '⌘/ Ctrl+/', action: 'Show shortcuts' },
  { key: 'Enter', action: 'Send message' },
  { key: 'Shift+Enter', action: 'New line' },
  { key: 'Tab', action: 'Autocomplete slash command' },
  { key: '↑ / ↓ (empty)', action: 'Navigate history' },
]
</script>
<template>
<el-dialog :model-value="props.show" title="Keyboard Shortcuts" width="380px" @update:model-value="emit('update:show',$event as boolean)">
<div style="font-family:var(--font-mono);font-size:12px;color:var(--color-orbit-text)">
<div v-for="s in shortcuts" :key="s.key" class="flex justify-between py-1.5" style="border-bottom:1px solid var(--color-orbit-border-light)">
<span style="color:var(--color-orbit-accent)">{{ s.key }}</span>
<span style="color:var(--color-orbit-text-secondary)">{{ s.action }}</span>
</div></div>
</el-dialog>
</template>
