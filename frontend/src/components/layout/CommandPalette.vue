<!-- UX-11: 命令面板——Cmd+K 全局命令搜索和执行 -->
<template>
  <Teleport to="body">
    <div v-if="visible" class="cmd-overlay" @click.self="close">
      <div class="cmd-modal">
        <input ref="inputRef" v-model="query" class="cmd-input" placeholder="Type a command..." @keydown="onKey" />
        <div class="cmd-list">
          <div v-for="(cmd, i) in filtered" :key="cmd.id" class="cmd-item" :class="{ active: i === idx }" @click="run(cmd)" @mouseenter="idx = i">
            <span class="cmd-icon">{{ cmd.icon }}</span>
            <span class="cmd-label">{{ cmd.label }}</span>
            <kbd class="cmd-shortcut">{{ cmd.shortcut }}</kbd>
          </div>
          <div v-if="!filtered.length" class="cmd-empty">No matching commands</div>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'

defineProps<{ visible: boolean }>()
const emit = defineEmits<{ (e: 'close'): void; (e: 'execute', cmd: string): void }>()

interface Cmd { id: string; icon: string; label: string; shortcut: string; action: string }
const CMDS: Cmd[] = [
  { id: 'files', icon: '📁', label: 'Toggle File Tree', shortcut: 'Ctrl+B', action: 'toggle:filetree' },
  { id: 'search', icon: '🔍', label: 'Search Files', shortcut: 'Ctrl+Shift+F', action: 'toggle:search' },
  { id: 'dag', icon: '🔀', label: 'Toggle DAG View', shortcut: '', action: 'toggle:dag' },
  { id: 'charts', icon: '📊', label: 'Toggle Charts', shortcut: '', action: 'toggle:charts' },
  { id: 'trace', icon: '🔎', label: 'Toggle Trace View', shortcut: '', action: 'toggle:trace' },
  { id: 'config', icon: '⚙️', label: 'Toggle Config', shortcut: '', action: 'toggle:config' },
  { id: 'settings', icon: '🎛️', label: 'Open Settings', shortcut: 'Ctrl+,', action: 'open:settings' },
  { id: 'theme', icon: '🌓', label: 'Toggle Theme', shortcut: '', action: 'toggle:theme' },
  { id: 'newsession', icon: '🆕', label: 'New Session', shortcut: 'Ctrl+N', action: 'open:newsession' },
  { id: 'shortcuts', icon: '⌨️', label: 'Keyboard Shortcuts', shortcut: 'Ctrl+/', action: 'open:shortcuts' },
  { id: 'reset', icon: '🔄', label: 'Reset Layout', shortcut: '', action: 'reset:layout' },
]

const query = ref('')
const idx = ref(0)
const inputRef = ref<HTMLInputElement | null>(null)

const filtered = computed(() => {
  const q = query.value.toLowerCase().trim()
  if (!q) return CMDS
  return CMDS.filter(c => c.label.toLowerCase().includes(q) || c.id.includes(q))
})

function onKey(e: KeyboardEvent) {
  if (e.key === 'Escape') { close(); return }
  if (e.key === 'ArrowDown') { e.preventDefault(); idx.value = (idx.value + 1) % filtered.value.length; return }
  if (e.key === 'ArrowUp') { e.preventDefault(); idx.value = (idx.value - 1 + filtered.value.length) % filtered.value.length; return }
  if (e.key === 'Enter' && filtered.value.length > 0) { run(filtered.value[idx.value]); return }
}

function run(cmd: Cmd) { emit('execute', cmd.action); close() }
function close() { query.value = ''; emit('close') }

onMounted(() => { inputRef.value?.focus() })
</script>

<style scoped>
.cmd-overlay { position:fixed;inset:0;z-index:10000;background:rgba(0,0,0,.5);display:flex;justify-content:center;padding-top:15vh }
.cmd-modal { width:480px;max-height:400px;background:var(--color-orbit-surface,#1a1a2e);border:1px solid var(--color-orbit-border);border-radius:8px;overflow:hidden;box-shadow:0 8px 32px rgba(0,0,0,.5) }
.cmd-input { width:100%;padding:12px 16px;border:none;border-bottom:1px solid var(--color-orbit-border);background:transparent;color:var(--color-orbit-text);font-size:14px;font-family:var(--font-mono);outline:none }
.cmd-list { max-height:300px;overflow-y:auto;padding:4px 0 }
.cmd-item { display:flex;align-items:center;gap:8px;padding:6px 16px;cursor:pointer;font-size:12px;color:var(--color-orbit-text-secondary) }
.cmd-item.active,.cmd-item:hover { background:var(--color-orbit-surface-hover);color:var(--color-orbit-text) }
.cmd-icon { font-size:14px;width:20px;text-align:center }
.cmd-label { flex:1 }
.cmd-shortcut { font-size:10px;padding:1px 6px;border-radius:3px;background:var(--color-orbit-surface);border:1px solid var(--color-orbit-border);font-family:var(--font-mono) }
.cmd-empty { padding:16px;text-align:center;color:var(--color-orbit-text-muted);font-size:12px }
</style>
