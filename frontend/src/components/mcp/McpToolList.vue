<script setup lang="ts">
import { computed, ref, onMounted } from 'vue'
import { useMcpStore } from '@/stores/mcp'
import type { McpTool } from '@/stores/mcp'

const props = defineProps<{ serverName: string }>()

const store = useMcpStore()
const search = ref('')

onMounted(() => {
  if (!store.tools[props.serverName]) {
    store.fetchTools(props.serverName)
  }
})

const filteredTools = computed(() => {
  const list = store.tools[props.serverName] || []
  if (!search.value) return list
  const q = search.value.toLowerCase()
  return list.filter(t => t.name.toLowerCase().includes(q) || (t.description || '').toLowerCase().includes(q))
})

function formatSchema(schema: Record<string, unknown>): string {
  if (!schema || !schema.properties) return '—'
  const props = schema.properties as Record<string, { type?: string }>
  return Object.entries(props).map(([k, v]) => `${k}: ${v?.type || 'any'}`).join(', ')
}

function schemaKeys(schema: Record<string, unknown>): string[] {
  if (!schema || !schema.properties) return []
  return Object.keys(schema.properties as Record<string, unknown>)
}
</script>

<template>
<div class="mcp-tool-list">
  <div class="tool-search-bar">
    <el-input
      v-model="search"
      placeholder="搜索工具名称或描述..."
      size="small"
      clearable
      class="tool-search-input"
    />
    <el-button size="small" @click="store.discoverTools(serverName)">重新发现</el-button>
  </div>

  <el-table
    :data="filteredTools"
    stripe
    size="small"
    max-height="360"
    style="width:100%"
    :empty-text="store.tools[serverName]?.length === 0 ? '暂无工具' : '无匹配'"
  >
    <el-table-column prop="name" label="工具名" width="180" />
    <el-table-column prop="description" label="描述" min-width="200" show-overflow-tooltip />
    <el-table-column label="参数" width="280">
      <template #default="{ row }: { row: McpTool }">
        <div class="schema-cell">
          <el-tag
            v-for="k in schemaKeys(row.input_schema)"
            :key="k"
            size="small"
            class="param-tag"
          >
            {{ k }}
          </el-tag>
          <span v-if="!schemaKeys(row.input_schema).length" class="no-params">无参数</span>
        </div>
      </template>
    </el-table-column>
    <el-table-column label="Schema" width="60">
      <template #default="{ row }: { row: McpTool }">
        <el-tooltip :content="formatSchema(row.input_schema)" placement="left">
          <el-tag size="small" type="info">JSON</el-tag>
        </el-tooltip>
      </template>
    </el-table-column>
  </el-table>
</div>
</template>

<style scoped>
.mcp-tool-list { padding-top: 8px; border-top: 1px solid var(--color-orbit-border, #2a2a4a); }
.tool-search-bar { display: flex; gap: 8px; margin-bottom: 8px; }
.tool-search-input { flex: 1; }
.schema-cell { display: flex; flex-wrap: wrap; gap: 3px; }
.param-tag { font-family: var(--font-mono, monospace); font-size: 10px; }
.no-params { color: #666; font-size: 11px; }

/* Element Plus 暗色覆盖 */
:deep(.el-table) { --el-table-bg-color: transparent; --el-table-tr-bg-color: transparent; --el-table-header-bg-color: rgba(255,255,255,.03); --el-table-row-hover-bg-color: rgba(255,255,255,.06); --el-table-border-color: rgba(255,255,255,.08); }
:deep(.el-table th.el-table__cell) { color: #999; font-weight: 600; font-size: 11px; }
:deep(.el-table td.el-table__cell) { color: #ccc; font-size: 12px; }
:deep(.el-input__wrapper) { background: rgba(255,255,255,.06); box-shadow: none; }
:deep(.el-input__inner) { color: #e0e0e0; }
</style>
