<!-- 测试覆盖空洞面板（PR6）——按函数名分析参数类型 × 已有测试值的缺口 -->
<script setup lang="ts">
import { ref } from 'vue'
import { useCodeGraphStore } from '@/stores/codegraph'

const store = useCodeGraphStore()
const funcName = ref('')

// P2-2: 防抖 300ms——阻止快速点击/连续回车触发冗余请求
let _debounce: ReturnType<typeof setTimeout> | undefined
function analyze() {
  const name = funcName.value.trim()
  if (!name) return
  if (_debounce) clearTimeout(_debounce)
  _debounce = setTimeout(() => store.fetchTestGaps(name), 300)
}
</script>

<template>
<div class="gaps-panel">
  <div class="gaps-input">
    <el-input
      v-model="funcName"
      size="small"
      placeholder="输入函数名，如 my_func"
      @keyup.enter="analyze"
    />
    <el-button size="small" type="primary" :loading="store.testGapsLoading" @click="analyze">分析</el-button>
  </div>

  <div v-if="store.testGaps" class="gaps-body">
    <div class="gaps-summary">
      <span class="gaps-func">{{ store.testGaps.function }}</span>
      <span class="gaps-total">{{ store.testGaps.total }} 处空洞</span>
    </div>
    <!-- P2-1: message 作为横幅提示，不压制表格；两者可共存 -->
    <div v-if="store.testGaps.message" class="gaps-msg">{{ store.testGaps.message }}</div>
    <table v-if="store.testGaps.gaps.length" class="gaps-table">
      <thead>
        <tr><th>参数</th><th>类型</th><th>已覆盖</th><th>缺失用例</th></tr>
      </thead>
      <tbody>
        <tr v-for="(g, i) in store.testGaps.gaps" :key="i">
          <td class="mono">{{ g.param }}</td>
          <td class="mono type">{{ g.type }}</td>
          <td>{{ g.covered.join(', ') || '—' }}</td>
          <td class="missing">{{ g.missing.join(', ') || '—' }}</td>
        </tr>
      </tbody>
    </table>
    <div v-else-if="!store.testGaps.message" class="gaps-empty">该函数无测试覆盖空洞 ✓</div>
  </div>
  <div v-else class="gaps-empty">输入函数名分析测试覆盖空洞</div>
</div>
</template>

<style scoped>
.gaps-panel { height: 100%; overflow-y: auto; font-size: 13px; padding: 8px 12px; }
.gaps-input { display: flex; gap: 8px; margin-bottom: 10px; }
.gaps-summary { display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px; }
.gaps-func { font-family: var(--font-mono); font-weight: 600; }
.gaps-total { font-size: 11px; color: var(--el-text-color-secondary); }
.gaps-msg { color: var(--el-color-warning); font-size: 12px; padding: 8px 0; }
.gaps-table { width: 100%; border-collapse: collapse; font-size: 12px; }
.gaps-table th, .gaps-table td { text-align: left; padding: 4px 6px; border-bottom: 1px solid var(--el-border-color-light); }
.gaps-table th { color: var(--el-text-color-secondary); font-weight: 500; }
.mono { font-family: var(--font-mono); }
.type { color: var(--el-color-primary); }
.missing { color: var(--el-color-danger); }
.gaps-empty { padding: 16px; color: var(--el-text-color-secondary); text-align: center; }
</style>
