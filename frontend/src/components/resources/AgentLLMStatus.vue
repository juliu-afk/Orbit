<!-- Agent LLM 配置状态面板 (Step 2.3) -->
<template>
  <el-card shadow="never" class="panel-card">
    <template #header>
      <div style="display:flex;justify-content:space-between;align-items:center">
        <span>Agent LLM 配置状态</span>
        <el-tag v-if="ccSwitchActive" type="warning" size="small">CC_SWITCH 生效中</el-tag>
      </div>
    </template>
    <el-table :data="agentRows" size="small" stripe>
      <el-table-column prop="name" label="Agent" width="130" />
      <el-table-column prop="model" label="当前模型" min-width="180">
        <template #default="{ row }">
          <el-tag :type="sourceTagType(row.source)" size="small" effect="plain">
            {{ row.model || '(本地规则)' }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="sourceLabel" label="来源" width="100">
        <template #default="{ row }">
          <span :style="{ color: sourceColor(row.source) }">
            {{ row.sourceLabel }}
            <el-icon v-if="row.isForced"><Lock /></el-icon>
          </span>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="100" fixed="right">
        <template #default="{ row }">
          <el-button size="small" text type="primary" @click="showHistory(row)">历史</el-button>
        </template>
      </el-table-column>
    </el-table>
  </el-card>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { Lock } from '@element-plus/icons-vue'

interface AgentLLMRow {
  name: string
  model: string
  source: string
  sourceLabel: string
  isForced: boolean
}

const agents = ['ArchitectAgent', 'DeveloperAgent', 'ReviewerAgent', 'QAAgent', 'ConfigAgent', 'ClarifierAgent']
const agentRows = ref<AgentLLMRow[]>([])
const ccSwitchActive = ref(false)

const sourceLabels: Record<string, string> = {
  cc_switch_force: 'CC_SWITCH',
  environment: '环境变量',
  cc_switch: 'CC_SWITCH',
  router: 'RouterAgent',
  default: '系统默认',
}

function sourceTagType(source: string): string {
  if (source === 'cc_switch_force' || source === 'cc_switch') return 'warning'
  if (source === 'environment') return 'success'
  if (source === 'router') return ''
  return 'info'
}

function sourceColor(source: string): string {
  if (source === 'cc_switch_force') return '#e6a23c'
  if (source === 'environment') return '#67c23a'
  return ''
}

async function fetchStatus() {
  const rows: AgentLLMRow[] = []
  for (const name of agents) {
    try {
      const resp = await fetch(`/api/v1/agents/${name}/llm`)
      const data = await resp.json()
      if (data.current) {
        rows.push({
          name,
          model: data.current.model,
          source: data.current.source,
          sourceLabel: sourceLabels[data.current.source] || data.current.source,
          isForced: data.current.is_forced,
        })
      }
      if (data.cc_switch_active) ccSwitchActive.value = true
    } catch {
      rows.push({ name, model: '—', source: 'default', sourceLabel: '未知', isForced: false })
    }
  }
  agentRows.value = rows
}

function showHistory(row: AgentLLMRow) {
  // TODO: Phase 2——展示模型切换历史
  console.log('show history for', row.name)
}

onMounted(fetchStatus)
</script>

<style scoped>
.panel-card {
  margin-bottom: 12px;
}
</style>
