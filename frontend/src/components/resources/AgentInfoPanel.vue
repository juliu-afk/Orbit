<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useAgentOpsStore } from '@/stores/agentops'
interface Row { name: string; model: string; source: string; sourceLabel: string; isForced: boolean }
const agentops = useAgentOpsStore()
const rows = ref<Row[]>([])
const ccActive = ref(false)
// P2-3 fix: 统一使用 apiGet，继承超时/AbortController/统一错误处理
import { apiGet } from '@/services/api'
async function fetchLLM(name: string): Promise<Row | null> {
  try {
    const data = await apiGet<{ name?: string; model?: string; source?: string; source_label?: string; is_forced?: boolean; cc_switch_active?: boolean }>(`/api/v1/agents/${name}/llm`)
    if (data.cc_switch_active) ccActive.value = true
    return { name: data.name || name, model: data.model || '', source: data.source || 'default', sourceLabel: data.source_label || 'default', isForced: data.is_forced || false }
  } catch { return null }
}
onMounted(async () => { const results = await Promise.all(['ArchitectAgent','DeveloperAgent','ReviewerAgent','QAAgent','ConfigAgent','ClarifierAgent'].map(fetchLLM)); rows.value = results.filter((r): r is Row => r !== null) })
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
