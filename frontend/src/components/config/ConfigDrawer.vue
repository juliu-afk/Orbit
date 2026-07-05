<script setup lang="ts">
import { ref, watch } from 'vue'
import { apiGet } from '@/services/api'
import YamlEditor from './YamlEditor.vue'
import VersionHistory from './VersionHistory.vue'
import BranchManager from './BranchManager.vue'

interface GitBranch { name: string; is_current: boolean; last_commit: string }

const props = defineProps<{ show: boolean }>()
const emit = defineEmits<{ (e: 'update:show', v: boolean): void }>()

const sections = ['model_routing', 'artifact_tiers', 'prompts', 'hallucination', 'trace']
const sectionLabels: Record<string, string> = {
  model_routing: '模型路由', artifact_tiers: '分级存储',
  prompts: 'Prompt', hallucination: '防幻觉', trace: 'Trace',
}
const activeTab = ref('edit')
const selectedSection = ref('')
const branches = ref<GitBranch[]>([])
const currentBranch = ref('main')

watch(() => props.show, async (visible) => {
  if (visible) await loadBranches()
})

async function loadBranches() {
  try {
    const data = await apiGet<GitBranch[]>('/api/v1/config/branches/list')
    branches.value = data || []
    currentBranch.value = data?.find(b => b.is_current)?.name || 'main'
  } catch { branches.value = [] }
}
</script>

<template>
<el-drawer
  :model-value="show"
  @update:model-value="emit('update:show', $event)"
  direction="rtl" size="800px" title="配置管理"
>
  <!-- 章节 + 分支 -->
  <div style="display:flex;gap:12px;align-items:center;margin-bottom:12px">
    <el-select v-model="selectedSection" placeholder="选择章节" style="flex:1">
      <el-option v-for="s in sections" :key="s" :label="sectionLabels[s]" :value="s" />
    </el-select>
    <span style="font-size:11px;color:var(--color-orbit-text-muted);font-family:var(--font-mono)">
      {{ currentBranch }}
    </span>
  </div>

  <!-- 标签页 -->
  <el-tabs v-model="activeTab" v-if="selectedSection">
    <el-tab-pane label="编辑" name="edit">
      <YamlEditor :section="selectedSection" />
    </el-tab-pane>
    <el-tab-pane label="历史" name="history">
      <VersionHistory :section="selectedSection" />
    </el-tab-pane>
    <el-tab-pane label="分支" name="branches">
      <BranchManager :branches="branches" :current="currentBranch" @reload="loadBranches" />
    </el-tab-pane>
  </el-tabs>

  <div v-else class="empty-state">选择配置章节以开始编辑</div>
</el-drawer>
</template>

<style scoped>
.empty-state { text-align:center;padding:60px;color:var(--color-orbit-text-muted);font-size:13px }
</style>
