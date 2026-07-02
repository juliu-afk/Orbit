<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useAgentOpsStore } from '@/stores/agentops'
import { apiGet } from '@/services/api'
interface Row { name: string; model: string; source: string; sourceLabel: string; isForced: boolean }
const agentops = useAgentOpsStore()
const rows = ref<Row[]>([])
const ccActive = ref(false)
async function fetchLLM(name: string): Promise<Row | null> {
  try {
    const data = await apiGet<{ name?: string; model?: string; source?: string; source_label?: string; is_forced?: boolean; cc_switch_active?: boolean }>(`/api/v1/agents/${name}/llm`)
    if (data.cc_switch_active) ccActive.value = true
    return { name: data.name || name, model: data.model || '', source: data.source || 'default', sourceLabel: data.source_label || 'default', isForced: data.is_forced || false }
  } catch { return null }
}
// v0.24: 恢复 apiGet fallback——后端 /api/v1/agents 可用时动态获取
const FALLBACK_AGENTS = ['ArchitectAgent','DeveloperAgent','ReviewerAgent','QAAgent','ConfigAgent','ClarifierAgent']
async function fetchAgentNames(): Promise<string[]> { try { const d = await apiGet<{ agents: Array<{ name: string }> }>('/api/v1/agents'); return d.agents?.map(a => a.name) || FALLBACK_AGENTS } catch { return FALLBACK_AGENTS } }
onMounted(async () => { const names = await fetchAgentNames(); const results = await Promise.all(names.map(fetchLLM)); rows.value = results.filter((r): r is Row => r !== null) })
</script>
<template>
<div class="flex flex-col h-full text-xs" style="font-family:var(--font-mono)">
  <div class="px-3 py-2 shrink-0 flex justify-between" style="border-bottom:1px solid var(--color-orbit-border);color:var(--color-orbit-text-muted)">
    <span class="tracking-wide uppercase">Agent LLM</span>
    <span v-if="ccActive" class="px-1.5 py-0.5 rounded text-[10px]" style="background:rgba(255,152,0,0.15);color:var(--color-orbit-warn)">CC_SWITCH</span>
  </div>
  <div class="flex-1 overflow-y-auto">
    <div v-for="r in rows" :key="r.name" class="flex justify-between px-3 py-1.5" style="border-bottom:1px solid var(--color-orbit-border-light);color:var(--color-orbit-text-secondary)">
      <span>{{ r.name }}</span>
      <span class="px-1.5 py-0.5 rounded text-[10px]" :style="{ background: r.model ? 'rgba(64,158,255,0.1)' : 'transparent', color: r.model ? 'var(--color-orbit-info)' : 'var(--color-orbit-text-muted)' }">{{ r.model || '--' }}</span>
    </div>
  </div>
  <div class="px-3 py-2 shrink-0" style="border-top:1px solid var(--color-orbit-border)">
    <div class="flex justify-between py-0.5"><span style="color:var(--color-orbit-text-muted)">active</span><span>{{ agentops.metrics?.active_tasks ?? '--' }}</span></div>
    <div class="flex justify-between py-0.5"><span style="color:var(--color-orbit-text-muted)">tokens</span><span>{{ agentops.metrics?.llm_tokens_total?.toLocaleString() ?? '--' }}</span></div>
    <div class="flex justify-between py-0.5"><span style="color:var(--color-orbit-text-muted)">intercepted</span><span>{{ agentops.metrics?.hallucination_intercepted_total ?? '--' }}</span></div>
  </div>
</div>
</template>
