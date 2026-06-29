<!-- 测试结果面板——pytest 结构化输出 + 失败→Diff 关联 -->
<template>
  <div class="test-panel">
    <div class="test-summary">
      <el-button size="small" type="primary" :loading="loading" @click="runTests">Run Tests</el-button>
      <span class="summary-item passed">{{ results.passed }} passed</span>
      <span class="summary-item failed">{{ results.failed }} failed</span>
      <span class="summary-item skipped">{{ results.skipped }} skipped</span>
    </div>
    <div v-if="results.cases.length" class="test-list">
      <div v-for="(t, i) in results.cases" :key="i" class="test-case" :class="'status-' + t.status">
        <span class="test-icon">{{ t.status === 'passed' ? '✓' : t.status === 'failed' ? '✗' : '○' }}</span>
        <span class="test-name">{{ t.name.split('::').pop() || t.name }}</span>
        <span class="test-file">{{ t.file.split('/').pop() }}</span>
        <span class="test-duration">{{ t.duration.toFixed(2) }}s</span>
        <el-button v-if="t.status === 'failed'" size="small" text type="danger" @click="$emit('show-error', t)">
          Details
        </el-button>
      </div>
    </div>
    <el-empty v-else-if="!loading" description="No test results" :image-size="40" />
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { apiGet } from '@/services/api'

interface TestCase { name: string; file: string; status: string; duration: number; error: string | null }
interface TestResults { passed: number; failed: number; skipped: number; total: number; cases: TestCase[] }

const results = ref<TestResults>({ passed: 0, failed: 0, skipped: 0, total: 0, cases: [] })
const loading = ref(false)

const emit = defineEmits<{ (e: 'show-error', t: TestCase): void }>()

async function runTests() {
  loading.value = true
  try {
    const data = await apiGet<TestResults>('/api/v1/tests/results')
    results.value = data
  } catch (e) {
    console.error('Test run failed:', e)
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.test-panel { padding: 8px; }
.test-summary { display: flex; align-items: center; gap: 12px; margin-bottom: 8px; }
.summary-item { font-size: 13px; font-weight: 500; }
.summary-item.passed { color: #67c23a; }
.summary-item.failed { color: #f56c6c; }
.summary-item.skipped { color: #e6a23c; }
.test-list { max-height: 300px; overflow-y: auto; }
.test-case { display: flex; align-items: center; gap: 6px; padding: 2px 4px; font-size: 13px; cursor: pointer; }
.test-case:hover { background: var(--el-fill-color-light); }
.test-icon { width: 16px; text-align: center; flex-shrink: 0; }
.test-case.status-passed .test-icon { color: #67c23a; }
.test-case.status-failed .test-icon { color: #f56c6c; }
.test-case.status-skipped .test-icon { color: #e6a23c; }
.test-name { flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.test-file { color: var(--el-text-color-secondary); font-size: 12px; }
.test-duration { color: var(--el-text-color-placeholder); font-size: 11px; }
</style>
