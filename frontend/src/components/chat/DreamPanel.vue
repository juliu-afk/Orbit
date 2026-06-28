<script setup lang="ts">
/** Dream 记忆合并触发组件——调用 /dream/run 进行 5 阶段记忆优化。

 * WHY: 后端 POST /api/v1/dream/run + GET /api/v1/dream/status 已实现但前端无入口。
 * P2-2/P2-3: 使用共享 apiPost/apiGet，显示具体错误消息。
 */
import { ref, onMounted } from 'vue'
import { apiPost, apiGet } from '@/services/api'

interface DreamStatus { status: string }

const status = ref<'idle' | 'running' | 'ready' | 'error'>('idle')
const loading = ref(false)
const dreamResult = ref<string | null>(null)
const error = ref<string | null>(null)

async function fetchStatus() {
  try {
    const data = await apiGet<DreamStatus>('/api/v1/dream/status')
    status.value = data?.status === 'ready' ? 'ready' : 'idle'
  } catch {
    status.value = 'error'
  }
}

async function triggerDream() {
  loading.value = true
  error.value = null
  dreamResult.value = null
  try {
    const data = await apiPost<Record<string, unknown>>('/api/v1/dream/run', {})
    status.value = 'ready'
    dreamResult.value = JSON.stringify(data, null, 2)
  } catch (e) {
    error.value = e instanceof Error ? e.message : '请求失败'
  } finally {
    loading.value = false
  }
}

onMounted(fetchStatus)
</script>

<template>
  <div class="dream-panel">
    <el-button size="small" :loading="loading" @click="triggerDream">
      {{ loading ? 'Dream 中...' : '记忆优化' }}
    </el-button>
    <span class="dream-status">{{ status === 'ready' ? '✅ 就绪' : '⏳ 待优化' }}</span>
    <div v-if="dreamResult" class="dream-result">
      <pre>{{ dreamResult }}</pre>
    </div>
    <div v-if="error" class="dream-error">{{ error }}</div>
  </div>
</template>

<style scoped>
.dream-panel { display: flex; align-items: center; gap: 8px; margin-top: 8px; }
.dream-status { font-size: 12px; color: #666; }
.dream-result { margin-top: 8px; background: #f5f5f5; padding: 6px; border-radius: 4px; max-height: 200px; overflow: auto; }
.dream-result pre { margin: 0; font-size: 11px; }
.dream-error { margin-top: 6px; color: #ff4d4f; font-size: 12px; }
</style>
