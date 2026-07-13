<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import { apiGet } from '@/services/api'
const emit = defineEmits<{ (e: 'send', text: string): void; (e: 'navigate-history', d: -1 | 1): void }>()
const inputRef = ref<HTMLTextAreaElement | null>(null)
const inputText = ref('')
// UX-1: 交互模式选择——四级权限（对标 Claude Code for VS Code）
// Manual=每次确认, Edit Automatically=读放行写首次确认, Plan=只读方案, Auto Mode=全自动
const MODES = ['Manual', 'Edit Automatically', 'Plan', 'Auto Mode'] as const
const currentMode = ref<string>('Auto Mode')
// UX-9: @-mention 自动完成——文件/符号/会话
const AT_TARGETS = ref<Array<{ name: string; type: 'file'|'symbol'|'session' }>>([])
const showAtMenu = ref(false)
const atIdx = ref(0)
const atQuery = ref('')
const FALLBACK_AT: typeof AT_TARGETS.value = [
  { name: 'src/orbit/', type: 'file' }, { name: 'tests/', type: 'file' },
  { name: 'CLAUDE.md', type: 'file' }, { name: 'AGENTS.md', type: 'file' },
]
// v0.24: 恢复 apiGet fallback——后端 /api/v1/terminal/commands 可用时动态获取
const FALLBACK_CMDS = ['/task', '/review', '/dream', '/search', '/help', '/compose']
const CMDS = ref<string[]>([...FALLBACK_CMDS])
onMounted(async () => { try { const d = await apiGet<{ commands: string[] }>('/api/v1/terminal/commands'); if (d.commands?.length) CMDS.value = d.commands } catch { /* fallback */ } })
const showAC = ref(false)
const acIdx = ref(0)
const filtered = computed(() => {
  if (!inputText.value.startsWith('/') || inputText.value.includes(' ')) return []
  return CMDS.value.filter(c => c.startsWith(inputText.value))
})
// WHY watch: 用户输入 "/" 或 "@" 时自动弹出补全
watch(inputText, (val) => {
  // / 命令补全
  if (val.startsWith('/') && !val.includes(' ') && filtered.value.length > 0) {
    showAC.value = true; acIdx.value = 0; showAtMenu.value = false
  } else if (!val.startsWith('/')) {
    showAC.value = false
  }
  // UX-9: @-mention 文件/符号引用
  const lastAt = val.lastIndexOf('@')
  if (lastAt >= 0 && (lastAt === 0 || val[lastAt - 1] === ' ')) {
    const q = val.slice(lastAt + 1).toLowerCase()
    AT_TARGETS.value = FALLBACK_AT.filter(t => t.name.toLowerCase().includes(q))
    if (AT_TARGETS.value.length > 0 && !val.includes(' ', lastAt + 1)) {
      showAtMenu.value = true; atIdx.value = 0; atQuery.value = q
    } else { showAtMenu.value = false }
  } else { showAtMenu.value = false }
})
function selectAc(cmd: string) {
  inputText.value = cmd
  showAC.value = false
  inputRef.value?.focus()
}
// UX-9: 选择 @-mention 目标
function selectAt(target: typeof AT_TARGETS.value[0]) {
  const lastAt = inputText.value.lastIndexOf('@')
  if (lastAt >= 0) {
    inputText.value = inputText.value.slice(0, lastAt) + '@' + target.name + ' '
  }
  showAtMenu.value = false
  inputRef.value?.focus()
}
function onKey(e: KeyboardEvent) {
  if (e.key === 'Enter' && !e.shiftKey) {
    // WHY: 如果补全菜单打开且有选中项，Enter 选中该项而非发送
    if (showAC.value && filtered.value.length > 0) {
      e.preventDefault()
      selectAc(filtered.value[acIdx.value])
      return
    }
    e.preventDefault(); const t = inputText.value.trim(); if (t) { emit('send', t); inputText.value = ''; showAC.value = false }
  }
  if (e.key === 'Tab') { e.preventDefault(); if (filtered.value.length > 0) { if (!showAC.value) { showAC.value = true } else { acIdx.value = (acIdx.value + 1) % filtered.value.length } } }
  if (e.key === 'ArrowUp') {
    if (showAC.value && filtered.value.length > 0) { e.preventDefault(); acIdx.value = (acIdx.value - 1 + filtered.value.length) % filtered.value.length; return }
    if (inputText.value === '') { e.preventDefault(); emit('navigate-history', -1) }
  }
  if (e.key === 'ArrowDown') {
    if (showAC.value && filtered.value.length > 0) { e.preventDefault(); acIdx.value = (acIdx.value + 1) % filtered.value.length; return }
    if (inputText.value === '') { e.preventDefault(); emit('navigate-history', 1) }
  }
  if (e.key === 'Escape') { showAC.value = false }
}
function focus() { inputRef.value?.focus() }
function setText(text: string) { inputText.value = text; inputRef.value?.focus() }
defineExpose({ focus, setText, currentMode })
</script>
<template>
<div class="input-box" style="position:relative">
  <!-- UX-1: 模式选择器——Manual/Edit Automatically/Plan/Auto Mode -->
  <div class="mode-bar">
    <button v-for="m in MODES" :key="m" class="mode-btn" :class="{ active: currentMode === m }" @click="currentMode = m">
      {{ m === 'Manual' ? '👆' : m === 'Edit Automatically' ? '✏️' : m === 'Plan' ? '📋' : '🤖' }} {{ m }}
    </button>
  </div>
  <div class="flex items-start gap-2 px-3 py-2">
    <textarea ref="inputRef" v-model="inputText" class="flex-1 resize-none outline-none" style="background:transparent;border:none;color:var(--color-orbit-text);font-family:var(--font-mono);font-size:13px;line-height:1.6;caret-color:var(--color-orbit-accent)" rows="1" :placeholder="currentMode === 'Manual' ? 'Manual mode — confirm each step...' : currentMode === 'Edit Automatically' ? 'Edit mode — auto-read, confirm-write...' : currentMode === 'Plan' ? 'Plan mode — read-only analysis...' : 'Auto Mode — /help...'" @keydown="onKey" />
  </div>
  <!-- WHY: 斜杠命令补全下拉——自动弹出，Tab/方向键选择，Enter 选中 -->
  <div v-if="showAC && filtered.length > 0" class="ac-dropdown">
    <div v-for="(cmd, i) in filtered" :key="cmd" class="ac-item" :class="{ 'ac-active': i === acIdx }" @mousedown.prevent="selectAc(cmd)" @mouseenter="acIdx = i">
      {{ cmd }}
    </div>
  </div>
  <!-- UX-9: @-mention 自动完成 -->
  <div v-if="showAtMenu && AT_TARGETS.length > 0" class="at-dropdown">
    <div v-for="(t, i) in AT_TARGETS" :key="t.name" class="at-item" :class="{ 'at-active': i === atIdx }" @mousedown.prevent="selectAt(t)" @mouseenter="atIdx = i">
      <span class="at-icon">{{ t.type === 'file' ? '📄' : t.type === 'symbol' ? '🔣' : '💬' }}</span>
      <span>{{ t.name }}</span>
      <span class="at-type">{{ t.type }}</span>
    </div>
  </div>
</div>
</template>
<style scoped>
.ac-dropdown {
  position: absolute; bottom: 100%; left: 0; right: 0;
  background: var(--color-orbit-surface); border: 1px solid var(--color-orbit-border);
  border-radius: 4px; margin: 0 8px 4px; max-height: 180px; overflow-y: auto;
  z-index: 100; font-family: var(--font-mono); font-size: 12px;
}
.ac-item {
  padding: 4px 12px; cursor: pointer; color: var(--color-orbit-text-secondary);
}
.ac-item:hover, .ac-active {
  background: var(--color-orbit-surface-hover); color: var(--color-orbit-text);
}
/* UX-9: @-mention dropdown */
.at-dropdown { position:absolute;bottom:100%;left:0;right:0;background:var(--color-orbit-surface);border:1px solid var(--color-orbit-accent);border-radius:4px;margin:0 8px 4px;max-height:160px;overflow-y:auto;z-index:100;font-size:11px }
.at-item { display:flex;align-items:center;gap:6px;padding:4px 10px;cursor:pointer;color:var(--color-orbit-text-secondary) }
.at-item:hover,.at-active { background:var(--color-orbit-surface-hover);color:var(--color-orbit-text) }
.at-icon { font-size:12px }.at-type { margin-left:auto;font-size:9px;color:var(--color-orbit-text-muted);text-transform:uppercase }
.mode-bar { display:flex; gap:2px; padding:4px 8px 0 }
.mode-btn {
  padding:2px 10px; border:none; border-radius:12px; cursor:pointer; font-size:11px;
  background:transparent; color:var(--color-orbit-text-secondary); font-family:var(--font-mono);
  transition: background .15s, color .15s;
}
.mode-btn:hover { background:var(--color-orbit-surface-hover); color:var(--color-orbit-text) }
.mode-btn.active { background:var(--color-orbit-accent); color:#fff }
</style>
