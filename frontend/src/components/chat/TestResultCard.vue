<!-- 测试结果摘要卡片——聊天流内嵌，默认折叠，按需展开 -->
<script setup lang="ts">
import { ref, computed } from 'vue'

interface TestSummary {
  passed: number
  failed: number
  skipped: number
  coverage_pct: number
  mutation_score?: number | null
  duration_sec: number
  repair_attempts: number
}

interface TestResult {
  type: 'test_result'
  summary: TestSummary
  verdict: string
  verdict_label: string
  verdict_color: string
  framework_warnings?: { severity: string; detail: string; suggestion?: string }[]
  errors?: string[]
  cross_report?: {
    consensus: string
    divergent_count: number
    divergent_points?: { target: string; reason: string; suggestion: string }[]
  }
  regression_tests_generated?: number
}

const props = defineProps<{ result: TestResult | null }>()

const collapsed = ref(true)
const showErrors = ref(false)

const hasWarnings = computed(() =>
  (props.result?.framework_warnings?.length ?? 0) > 0
)
const hasDivergence = computed(() =>
  (props.result?.cross_report?.divergent_count ?? 0) > 0
)
const isGreen = computed(() => props.result?.verdict_color === 'green')
const isRed = computed(() => props.result?.verdict_color === 'red')
const isYellow = computed(() => props.result?.verdict_color === 'yellow')

const consensusLabel = computed(() => {
  const c = props.result?.cross_report?.consensus
  if (c === 'aligned') return '🟢 测试+审查一致'
  if (c === 'divergent') return '🟡 有分歧需决策'
  if (c === 'test_only') return '📋 仅测试'
  if (c === 'review_only') return '🔍 仅审查'
  return ''
})
</script>

<template>
  <div v-if="result" class="test-result-card" :class="{ collapsed, green: isGreen, red: isRed, yellow: isYellow }">
    <!-- 摘要行——默认可见 -->
    <div class="trc-summary" @click="collapsed = !collapsed">
      <span class="trc-passed">✓ {{ result.summary.passed }}</span>
      <span v-if="result.summary.failed" class="trc-failed">✗ {{ result.summary.failed }}</span>
      <span v-if="result.summary.skipped" class="trc-skipped">○ {{ result.summary.skipped }}</span>
      <span class="trc-coverage">
        <span class="trc-cov-bar" :style="{ width: result.summary.coverage_pct + '%' }" />
        {{ result.summary.coverage_pct }}%
      </span>
      <span v-if="result.summary.mutation_score != null" class="trc-mutation">
        🧬 {{ result.summary.mutation_score }}%
      </span>
      <span class="trc-time">⏱ {{ result.summary.duration_sec }}s</span>
      <span v-if="result.summary.repair_attempts" class="trc-repairs">
        🔧 ×{{ result.summary.repair_attempts }}
      </span>
      <span v-if="result.regression_tests_generated" class="trc-regression">
        📝 +{{ result.regression_tests_generated }}
      </span>
      <span class="trc-verdict" :class="result.verdict_color">
        {{ result.verdict_label }}
      </span>
      <span v-if="hasWarnings" class="trc-warn-badge">
        ⚠️ {{ result.framework_warnings?.length }}
      </span>
      <span v-if="hasDivergence" class="trc-diverge-badge">
        ⚡ {{ result.cross_report?.divergent_count }}
      </span>
      <button class="trc-expand">{{ collapsed ? '展开' : '折叠' }}</button>
    </div>

    <!-- 详情——折叠时隐藏 -->
    <div v-if="!collapsed" class="trc-detail">
      <!-- 错误列表 -->
      <div v-if="result.errors?.length" class="trc-errors">
        <button class="trc-err-toggle" @click="showErrors = !showErrors">
          {{ showErrors ? '隐藏' : '查看' }} {{ result.errors.length }} 条错误
        </button>
        <pre v-if="showErrors" class="trc-err-list">{{ result.errors.join('\n') }}</pre>
      </div>

      <!-- 框架警告 -->
      <div v-if="hasWarnings" class="trc-warnings">
        <div v-for="(w, i) in result.framework_warnings" :key="i" class="trc-warn-item">
          <span class="trc-warn-sev" :class="w.severity">{{ w.severity === 'blocking' ? '🔴' : '⚠️' }}</span>
          <span class="trc-warn-detail">{{ w.detail }}</span>
          <span v-if="w.suggestion" class="trc-warn-sugg">{{ w.suggestion }}</span>
        </div>
      </div>

      <!-- CrossReport 共识 -->
      <div v-if="result.cross_report" class="trc-consensus">
        <div class="trc-consensus-label">{{ consensusLabel }}</div>
        <div v-if="hasDivergence" class="trc-divergent">
          <div v-for="(d, i) in result.cross_report.divergent_points" :key="i" class="trc-div-item">
            <div class="trc-div-target">{{ d.target }}</div>
            <div class="trc-div-reason">{{ d.reason }}</div>
            <div v-if="d.suggestion" class="trc-div-sugg">建议: {{ d.suggestion }}</div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.test-result-card {
  margin: 4px 0; border-radius: 4px;
  background: rgba(15, 15, 26, 0.9); border: 1px solid var(--color-orbit-border);
  font-size: 12px; line-height: 1.5; overflow: hidden;
}
.test-result-card.green { border-left: 3px solid #67c23a; }
.test-result-card.red   { border-left: 3px solid #f56c6c; }
.test-result-card.yellow{ border-left: 3px solid #e6a23c; }

.trc-summary {
  display: flex; align-items: center; gap: 8px; padding: 6px 10px;
  cursor: pointer; user-select: none; flex-wrap: wrap;
  color: var(--color-orbit-text);
}
.trc-summary:hover { background: rgba(255,255,255,0.03); }
.trc-passed { color: #67c23a; font-weight: 600; }
.trc-failed { color: #f56c6c; font-weight: 600; }
.trc-skipped { color: #e6a23c; }
.trc-coverage { display: inline-flex; align-items: center; gap: 3px; color: var(--color-orbit-text-secondary); }
.trc-cov-bar { display: inline-block; height: 8px; background: #67c23a; border-radius: 4px; min-width: 16px; }
.trc-mutation { color: var(--color-orbit-text-secondary); }
.trc-time { color: var(--color-orbit-text-muted); font-size: 11px; }
.trc-repairs { color: #e6a23c; }
.trc-regression { color: #409eff; }
.trc-verdict { font-weight: 600; padding: 0 6px; border-radius: 3px; font-size: 11px; }
.trc-verdict.green { background: rgba(103,194,58,0.15); color: #67c23a; }
.trc-verdict.red   { background: rgba(245,108,108,0.15); color: #f56c6c; }
.trc-verdict.yellow{ background: rgba(230,162,60,0.15); color: #e6a23c; }
.trc-warn-badge { background: rgba(230,162,60,0.15); color: #e6a23c; padding: 0 4px; border-radius: 3px; font-size: 11px; }
.trc-diverge-badge { background: rgba(64,158,255,0.15); color: #409eff; padding: 0 4px; border-radius: 3px; font-size: 11px; }
.trc-expand { background: none; border: 1px solid var(--color-orbit-border); color: var(--color-orbit-text-muted); cursor: pointer; font-size: 11px; padding: 1px 8px; border-radius: 3px; font-family: var(--font-mono); }
.trc-expand:hover { border-color: var(--color-orbit-accent); color: var(--color-orbit-accent); }

.trc-detail { padding: 6px 10px 10px; border-top: 1px solid rgba(255,255,255,0.05); }
.trc-errors { margin-bottom: 6px; }
.trc-err-toggle { background: none; border: none; color: #f56c6c; cursor: pointer; font-size: 11px; font-family: var(--font-mono); }
.trc-err-list { margin: 4px 0 0; padding: 6px 8px; background: rgba(245,108,108,0.08); border-radius: 3px; color: #f56c6c; font-size: 11px; white-space: pre-wrap; word-break: break-all; max-height: 150px; overflow-y: auto; }

.trc-warnings { margin-bottom: 6px; }
.trc-warn-item { display: flex; align-items: flex-start; gap: 4px; padding: 2px 0; font-size: 11px; }
.trc-warn-sev { flex-shrink: 0; }
.trc-warn-detail { color: var(--color-orbit-text-secondary); flex: 1; }
.trc-warn-sugg { color: var(--color-orbit-text-muted); font-size: 10px; }

.trc-consensus { font-size: 11px; }
.trc-consensus-label { color: var(--color-orbit-text-secondary); margin-bottom: 4px; }
.trc-div-item { padding: 4px 6px; margin-bottom: 4px; background: rgba(64,158,255,0.06); border-radius: 3px; }
.trc-div-target { color: #409eff; font-weight: 500; }
.trc-div-reason { color: var(--color-orbit-text); }
.trc-div-sugg { color: var(--color-orbit-text-muted); font-size: 10px; }
</style>
