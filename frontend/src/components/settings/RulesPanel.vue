<!-- UX-10: Rules 面板——AGENTS.md 编辑器 + Memory 浏览器 -->
<template>
  <div class="rules-panel">
    <div class="rules-tabs">
      <button :class="{ active: tab === 'rules' }" @click="tab = 'rules'">AGENTS.md</button>
      <button :class="{ active: tab === 'memory' }" @click="tab = 'memory'">Memory</button>
    </div>

    <!-- AGENTS.md 编辑 -->
    <div v-if="tab === 'rules'" class="rules-editor">
      <textarea v-model="rulesText" class="rules-textarea" placeholder="# AGENTS.md&#10;&#10;Project-specific instructions for AI agents..." />
      <div class="rules-actions">
        <button class="rules-save" @click="saveRules">Save</button>
        <span class="rules-hint" v-if="!saveMsg">Saved to project root AGENTS.md</span>
        <span class="rules-hint" style="color:var(--color-orbit-error)" v-else>{{ saveMsg }}</span>
      </div>
    </div>

    <!-- Memory 浏览器 -->
    <div v-if="tab === 'memory'" class="memory-list">
      <div v-if="loadError" class="memory-empty" style="color:var(--color-orbit-warn)">{{ loadError }}</div>
      <div v-else-if="!memories.length" class="memory-empty">No memories yet. Agent decisions and learnings appear here.</div>
      <div v-for="m in memories" :key="m.id" class="memory-item">
        <div class="memory-type">{{ m.type }}</div>
        <div class="memory-text">{{ m.text }}</div>
        <div class="memory-time">{{ m.time }}</div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'

const tab = ref<'rules' | 'memory'>('rules')
const rulesText = ref('')
const memories = ref<Array<{ id: string; type: string; text: string; time: string }>>([])
const loadError = ref('')
const saveMsg = ref('')  // P2: 保存状态反馈

// 加载 AGENTS.md + Memory
onMounted(async () => {
  try {
    const resp = await fetch('/api/v1/files/read?path=AGENTS.md')
    if (resp.ok) rulesText.value = await resp.text()
  } catch { rulesText.value = '# AGENTS.md\n\n(无法读取——请手动创建)' }
  try {
    const resp = await fetch('/api/v1/memory/list')
    if (resp.ok) {
      const data = await resp.json()
      memories.value = (data.data || data || []).slice(0, 20)
    }
  } catch { loadError.value = 'Memory API 不可用' }
})

async function saveRules() {
  saveMsg.value = ''
  try {
    const resp = await fetch('/api/v1/files/write', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ path: 'AGENTS.md', content: rulesText.value }),
    })
    saveMsg.value = resp.ok ? 'Saved' : 'Save failed'
  } catch { saveMsg.value = 'API 不可用' }
}
</script>

<style scoped>
.rules-panel { height:100%;display:flex;flex-direction:column;background:var(--color-orbit-glass);font-family:var(--font-mono);font-size:12px }
.rules-tabs { display:flex;border-bottom:1px solid var(--color-orbit-border) }
.rules-tabs button { flex:1;padding:8px;border:none;background:transparent;color:var(--color-orbit-text-secondary);cursor:pointer;font-size:12px;font-family:var(--font-mono) }
.rules-tabs button.active { color:var(--color-orbit-accent);border-bottom:2px solid var(--color-orbit-accent) }
.rules-editor { flex:1;display:flex;flex-direction:column;padding:8px }
.rules-textarea { flex:1;background:var(--color-orbit-surface);border:1px solid var(--color-orbit-border);border-radius:4px;color:var(--color-orbit-text);font-size:12px;font-family:var(--font-mono);padding:8px;resize:none;outline:none }
.rules-actions { display:flex;align-items:center;gap:8px;padding:8px 0 }
.rules-save { padding:4px 12px;border:1px solid var(--color-orbit-accent);border-radius:4px;background:transparent;color:var(--color-orbit-accent);cursor:pointer;font-size:11px }
.rules-hint { font-size:10px;color:var(--color-orbit-text-muted) }
.memory-list { flex:1;overflow-y:auto;padding:8px }
.memory-empty { padding:16px;text-align:center;color:var(--color-orbit-text-muted) }
.memory-item { padding:8px;border-bottom:1px solid var(--color-orbit-border) }
.memory-type { font-size:10px;color:var(--color-orbit-accent);text-transform:uppercase;margin-bottom:2px }
.memory-text { color:var(--color-orbit-text) }
.memory-time { font-size:10px;color:var(--color-orbit-text-muted);margin-top:4px }
</style>
