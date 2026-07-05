<script setup lang="ts">
import { ref, watch, computed } from 'vue'
import { apiGet } from '@/services/api'

interface TraceSpan {
  span_id: string
  parent_span_id: string | null
  name: string
  kind: string
  start_time: number
  end_time: number
  duration_ms: number
  status: string
  attributes: Record<string, string>
}

interface TraceTask {
  task_id: string
  span_count: number
  last_seen: string
}

const props = defineProps<{ show: boolean }>()
const emit = defineEmits<{ (e: 'update:show', v: boolean): void }>()

const tasks = ref<TraceTask[]>([])
const spans = ref<TraceSpan[]>([])
const selectedTask = ref<string | null>(null)
const selectedSpan = ref<TraceSpan | null>(null)
const totalDuration = ref(0)
const loading = ref(false)

// 颜色映射——span kind → SVG 色块
const kindColor: Record<string, string> = {
  scheduler: '#6366f1',
  agent: '#10b981',
  tool: '#f59e0b',
  validator: '#ef4444',
  checkpoint: '#8b5cf6',
}
const defaultColor = '#6b7280'

watch(() => props.show, async (visible) => {
  if (visible) {
    await loadTasks()
  }
})

async function loadTasks() {
  try {
    const data = await apiGet<TraceTask[]>('/api/v1/observability/trace/recent?limit=30')
    tasks.value = data || []
  } catch { tasks.value = [] }
}

async function selectTask(taskId: string) {
  selectedTask.value = taskId
  loading.value = true
  try {
    const data = await apiGet<{
      task_id: string; root_spans: TraceSpan[]
      total_duration_ms: number; span_count: number
    }>(`/api/v1/observability/trace/${taskId}`)
    spans.value = data?.root_spans || []
    totalDuration.value = data?.total_duration_ms || 1
  } catch { spans.value = [] }
  loading.value = false
}

async function exportOtel() {
  if (!selectedTask.value) return
  const blob = await fetch(
    `/api/v1/observability/trace/${selectedTask.value}/export`
  ).then(r => r.blob())
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url; a.download = `trace-${selectedTask.value}.json`; a.click()
  URL.revokeObjectURL(url)
}

// 展平嵌套 span → 缩进层级
function flattenSpans(
  list: TraceSpan[], depth: number = 0
): (TraceSpan & { _depth: number })[] {
  return list.flatMap(s => [
    { ...s, _depth: depth },
    ...flattenSpans(
      spans.value.filter(c => c.parent_span_id === s.span_id), depth + 1
    ),
  ])
}

const flatSpans = computed(() => flattenSpans(spans.value.filter(s => !s.parent_span_id)))

function barX(s: TraceSpan): number {
  return totalDuration.value > 0
    ? (s.start_time - (spans.value[0]?.start_time || s.start_time)) / totalDuration.value * 100
    : 0
}
function barW(s: TraceSpan): number {
  return Math.max(2, (s.duration_ms / totalDuration.value) * 100)
}
</script>

<template>
<el-drawer
  :model-value="show"
  @update:model-value="emit('update:show', $event)"
  direction="rtl" size="700px" title="Trace 链路追踪"
>
  <!-- 任务选择 -->
  <div style="margin-bottom:12px">
    <el-select
      v-model="selectedTask" placeholder="选择任务"
      style="width:100%" filterable
      @change="selectTask"
    >
      <el-option v-for="t in tasks" :key="t.task_id"
        :label="`${t.task_id} (${t.span_count} spans)`"
        :value="t.task_id"
      />
    </el-select>
  </div>

  <!-- 空态 -->
  <div v-if="tasks.length === 0" class="empty-state">
    暂无 Trace 数据
  </div>

  <!-- 加载 -->
  <div v-if="loading" class="empty-state">加载中...</div>

  <!-- 瀑布图 -->
  <div v-if="!loading && flatSpans.length > 0" style="overflow-x:auto">
    <div style="font-size:11px;color:var(--color-orbit-text-muted);margin-bottom:4px">
      {{ flatSpans.length }} spans · {{ totalDuration }}ms
    </div>
    <svg :width="flatSpans.length * 24 + 600" :height="flatSpans.length * 24 + 30">
      <g v-for="(s, i) in flatSpans" :key="s.span_id">
        <text
          :x="0" :y="i * 24 + 18" font-size="11"
          :fill="kindColor[s.kind] || defaultColor"
          style="font-family:var(--font-mono)"
        >{{ '  '.repeat(s._depth) }}{{ s.name }}</text>
        <rect
          :x="barX(s) * 5 + 320" :y="i * 24 + 6"
          :width="barW(s) * 5" height="14" rx="3"
          :fill="kindColor[s.kind] || defaultColor" opacity="0.8"
          @click="selectedSpan = s"
          style="cursor:pointer"
        />
        <text
          :x="barX(s) * 5 + barW(s) * 5 + 326" :y="i * 24 + 18"
          font-size="10" fill="var(--color-orbit-text-muted)"
          style="font-family:var(--font-mono)"
        >{{ s.duration_ms }}ms</text>
      </g>
    </svg>
  </div>

  <!-- Span 详情 -->
  <div v-if="selectedSpan" style="margin-top:16px;padding:12px;background:rgba(255,255,255,.03);border-radius:6px">
    <div style="font-weight:600;margin-bottom:8px">{{ selectedSpan.name }}</div>
    <div class="kv"><span class="k">Kind</span><span class="v">{{ selectedSpan.kind }}</span></div>
    <div class="kv"><span class="k">Duration</span><span class="v">{{ selectedSpan.duration_ms }}ms</span></div>
    <div class="kv"><span class="k">Status</span><span class="v" :style="{color:selectedSpan.status==='error'?'#ef4444':'#10b981'}">{{ selectedSpan.status }}</span></div>
    <div v-for="(v, k) in selectedSpan.attributes" :key="k" class="kv">
      <span class="k">{{ k }}</span><span class="v">{{ v }}</span>
    </div>
  </div>

  <!-- 导出 -->
  <div v-if="selectedTask" style="margin-top:12px">
    <el-button size="small" @click="exportOtel">导出 OTEL JSON</el-button>
  </div>
</el-drawer>
</template>

<style scoped>
.empty-state { text-align:center;padding:40px;color:var(--color-orbit-text-muted);font-size:13px }
.kv { display:flex;gap:12px;font-size:12px;margin-bottom:4px;font-family:var(--font-mono) }
.k { color:var(--color-orbit-text-muted);min-width:80px }
.v { color:var(--color-orbit-text-primary);word-break:break-all }
</style>
