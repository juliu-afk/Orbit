<!-- 快速修复面板——Lightbulb/Code Actions (Phase 2.3) -->
<template>
  <div class="code-actions">
    <div class="actions-header">Quick Actions</div>
    <el-button size="small" @click="runRuff">Format (ruff)</el-button>
    <el-button size="small" @click="runMyPy">Type check (mypy)</el-button>
    <el-button size="small" @click="organizeImports">Organize Imports</el-button>
    <div v-if="result" class="action-result">{{ result }}</div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { apiPost } from '@/services/api'

const emit = defineEmits<{ (e: 'refresh'): void }>()
const result = ref('')

async function runRuff() {
  result.value = ''
  try {
    const res = await apiPost<{ exit_code: number; stdout: string }>('/api/v1/terminal/exec', { command: 'ruff check --fix .', timeout: 30 })
    result.value = res.stdout ? 'Formatted' : 'No issues'
    emit('refresh')
  } catch (e: unknown) { result.value = (e as Error).message || 'Failed' }
}

async function runMyPy() {
  result.value = 'Running...'
  try {
    const res = await apiPost<{ exit_code: number; stdout: string }>('/api/v1/terminal/exec', { command: 'mypy --strict .', timeout: 60 })
    result.value = res.exit_code === 0 ? 'No type errors' : res.stdout.slice(-200)
  } catch (e: unknown) { result.value = (e as Error).message || 'Failed' }
}

async function organizeImports() {
  result.value = ''
  try {
    const res = await apiPost<{ exit_code: number }>('/api/v1/terminal/exec', { command: 'ruff check --select I --fix .', timeout: 15 })
    result.value = res.exit_code === 0 ? 'Imports organized' : 'Check terminal for details'
    emit('refresh')
  } catch (e: unknown) { result.value = (e as Error).message || 'Failed' }
}
</script>

<style scoped>
.code-actions { padding: 8px; display: flex; flex-wrap: wrap; gap: 8px; align-items: center; }
.actions-header { width: 100%; font-weight: 600; font-size: 13px; margin-bottom: 4px; }
.action-result { width: 100%; font-size: 12px; color: var(--el-text-color-secondary); margin-top: 4px; }
</style>
