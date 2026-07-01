<script setup lang="ts">
// WHY 新建：替代 AgentLLMStatus.vue + DashboardView 右侧 sidebar。
// 去掉 el-card/el-table/el-tag 等 Element Plus 依赖，用 Tailwind 重写。
// 数据获取逻辑保留——GET /api/v1/agents/{name}/llm
import { ref, onMounted } from 'vue'
import { useAgentOpsStore } from '@/stores/agentops'

interface AgentLLMRow {
  name: string
  model: string
  source: string
  sourceLabel: string
  isForced: boolean
}

const agentops = useAgentOpsStore()

const agents = ['ArchitectAgent', 'DeveloperAgent', 'ReviewerAgent', 'QAAgent', 'ConfigAgent', 'ClarifierAgent']
const agentRows = ref<AgentLLMRow[]>([])
const ccSwitchActive = ref(false)

// WHY 保留原有数据获取：直接 fetch Agent LLM 配置，不走 store（简单数据只读展示）
async function fetchAgentLLM(name: string): Promise<AgentLLMRow | null> {
  try {
    const resp = await fetch(`/api/v1/agents/${name}/llm`)
    const json = await resp.json()
    if (json.code === 0 && json.data) {
      if (json.data.cc_switch_active) ccSwitchActive.value = true
      return {
        name: json.data.name || name,
        model: json.data.model || '',
        source: json.data.source || 'default',
        sourceLabel: json.data.source_label || json.data.source || 'default',
        isForced: json.data.is_forced || false,
      }
    }
  } catch {
    // 后端不可用则跳过
  }
  return null
}

onMounted(async () => {
  const results = await Promise.all(agents.map(fetchAgentLLM))
  agentRows.value = results.filter((r): r is AgentLLMRow => r !== null)
})
</script>

<template>
  <div class="agent-info-panel flex flex-col h-full text-xs" style="font-family: var(--font-mono);">
    <!-- 标题 -->
    <div
      class="panel-header px-3 py-2 shrink-0"
      style="
        border-bottom: 1px solid var(--color-orbit-border);
        color: var(--color-orbit-text-muted);
      "
    >
      <div class="flex items-center justify-between">
        <span class="tracking-wide uppercase">Agent LLM</span>
        <span
          v-if="ccSwitchActive"
          class="px-1.5 py-0.5 rounded text-[10px]"
          style="background: rgba(255,152,0,0.15); color: var(--color-orbit-warn);"
        >
          CC_SWITCH
        </span>
      </div>
    </div>

    <!-- Agent 列表 -->
    <div class="agent-list flex-1 overflow-y-auto">
      <div
        v-for="row in agentRows"
        :key="row.name"
        class="agent-row px-3 py-1.5 flex items-center justify-between"
        style="border-bottom: 1px solid var(--color-orbit-border-light);"
      >
        <span style="color: var(--color-orbit-text-secondary);">
          {{ row.name }}
        </span>
        <div class="flex items-center gap-1.5">
          <span
            class="px-1.5 py-0.5 rounded text-[10px]"
            :style="{
              background: row.model ? 'rgba(64,158,255,0.1)' : 'transparent',
              color: row.model ? 'var(--color-orbit-info)' : 'var(--color-orbit-text-muted)',
            }"
          >
            {{ row.model || '—' }}
          </span>
        </div>
      </div>
    </div>

    <!-- 指标摘要 -->
    <div
      class="metrics-section px-3 py-2 shrink-0"
      style="border-top: 1px solid var(--color-orbit-border);"
    >
      <div class="flex justify-between py-0.5">
        <span style="color: var(--color-orbit-text-muted);">活跃任务</span>
        <span style="color: var(--color-orbit-text);">
          {{ agentops.metrics?.active_tasks ?? '—' }}
        </span>
      </div>
      <div class="flex justify-between py-0.5">
        <span style="color: var(--color-orbit-text-muted);">Token 消耗</span>
        <span style="color: var(--color-orbit-text);">
          {{ agentops.metrics?.llm_tokens_total?.toLocaleString() ?? '—' }}
        </span>
      </div>
      <div class="flex justify-between py-0.5">
        <span style="color: var(--color-orbit-text-muted);">防幻觉拦截</span>
        <span style="color: var(--color-orbit-text);">
          {{ agentops.metrics?.hallucination_intercepted_total ?? '—' }}
        </span>
      </div>
      <div class="flex justify-between py-0.5">
        <span style="color: var(--color-orbit-text-muted);">沙箱可用</span>
        <span style="color: var(--color-orbit-text);">
          {{ agentops.metrics?.sandbox_pool_available ?? '—' }}
        </span>
      </div>
    </div>
  </div>
</template>

<style scoped>
.agent-row:hover {
  background: var(--color-orbit-surface-hover);
}
</style>
