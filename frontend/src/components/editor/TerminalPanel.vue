<!-- 集成终端面板——xterm.js 风格命令执行器 -->
<template>
  <div class="terminal-panel">
    <div class="term-output" ref="outputRef">
      <div v-for="(entry, i) in history" :key="i" class="term-entry">
        <div class="term-prompt">$ {{ entry.command }}</div>
        <pre class="term-stdout" v-if="entry.stdout">{{ entry.stdout }}</pre>
        <pre class="term-stderr" v-if="entry.stderr">{{ entry.stderr }}</pre>
        <div class="term-exit" v-if="entry.exitCode !== null">Exit: {{ entry.exitCode }} ({{ entry.duration }}ms)</div>
      </div>
    </div>
    <div class="term-input-row">
      <span class="term-prompt">$</span>
      <input ref="inputRef" v-model="input" class="term-input" @keyup.enter="execute" placeholder="command..." />
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, nextTick } from 'vue'
import { apiPost } from '@/services/api'

interface TermEntry { command: string; stdout: string; stderr: string; exitCode: number | null; duration: number }

// P1: 最大输出条目——防大输出时浏览器卡死
// P2-1 (#152): 支持 localStorage 覆盖默认值
const MAX_ENTRIES = parseInt(
  localStorage.getItem('terminal.max_entries') || '100', 10
)

const input = ref('')
const loading = ref(false)
const history = ref<TermEntry[]>([])
const outputRef = ref<HTMLDivElement>()
const inputRef = ref<HTMLInputElement>()

async function execute() {
  const cmd = input.value.trim()
  if (!cmd) return
  input.value = ''
  loading.value = true
  try {
    const res = await apiPost<{ exit_code: number; stdout: string; stderr: string; duration_ms: number }>(
      '/api/v1/terminal/exec', { command: cmd, timeout: 30 }
    )
    history.value.push({ command: cmd, stdout: res.stdout, stderr: res.stderr, exitCode: res.exit_code, duration: Math.round(res.duration_ms) })
  } catch (e: any) {
    history.value.push({ command: cmd, stdout: '', stderr: e.message || 'Command failed', exitCode: -1, duration: 0 })
  } finally {
    // P1: 超限时移除最旧条目——防大输出卡死浏览器
    if (history.value.length > MAX_ENTRIES) {
      history.value = history.value.slice(-MAX_ENTRIES)
    }
    loading.value = false
    await nextTick()
    outputRef.value?.scrollTo(0, outputRef.value.scrollHeight)
  }
}
</script>

<style scoped>
.terminal-panel { height: 100%; display: flex; flex-direction: column; background: #1e1e1e; color: #d4d4d4; font-family: 'Consolas','Courier New',monospace; font-size: 13px; }
.term-output { flex: 1; overflow-y: auto; padding: 8px; }
.term-entry { margin-bottom: 4px; }
.term-prompt { color: #6a9955; }
.term-stdout { margin: 0; white-space: pre-wrap; word-break: break-all; color: #d4d4d4; }
.term-stderr { margin: 0; white-space: pre-wrap; word-break: break-all; color: #f48771; }
.term-exit { color: #808080; font-size: 11px; }
.term-input-row { display: flex; align-items: center; padding: 4px 8px; border-top: 1px solid #333; }
.term-input { flex: 1; background: transparent; border: none; color: #d4d4d4; font-family: inherit; font-size: inherit; outline: none; }
</style>
