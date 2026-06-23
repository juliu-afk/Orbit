<!-- Token 消耗折线图：ECharts 渲染，双 Y 轴 + 100 点窗口 -->
<template>
  <div class="chart-wrapper">
    <div v-if="dataPoints.length === 0" class="chart-empty">
      <el-empty description="暂无 Token 数据" :image-size="80" />
    </div>
    <div ref="chartRef" class="chart-container" :class="{ hidden: dataPoints.length === 0 }" />
  </div>
</template>

<script setup lang="ts">
import { onMounted, onUnmounted, ref, watch } from 'vue'
import * as echarts from 'echarts'
import type { TokenPoint } from '@/types/dashboard'

const props = defineProps<{
  dataPoints: TokenPoint[]
}>()

const chartRef = ref<HTMLElement | null>(null)
let chart: echarts.ECharts | null = null
let resizeObserver: ResizeObserver | null = null

onMounted(() => {
  if (!chartRef.value) return
  chart = echarts.init(chartRef.value)
  chart.setOption({
    tooltip: { trigger: 'axis' },
    legend: { data: ['Prompt Tokens', 'Completion Tokens', 'Total'], textStyle: { color: '#a0a0a0' } },
    grid: { left: 50, right: 60, top: 40, bottom: 30 },
    xAxis: {
      type: 'category',
      data: [],
      axisLabel: { color: '#808080', fontSize: 10 },
    },
    yAxis: [
      {
        type: 'value',
        name: 'Tokens/次',
        nameTextStyle: { color: '#808080' },
        axisLabel: { color: '#808080' },
      },
      {
        type: 'value',
        name: '累计',
        nameTextStyle: { color: '#808080' },
        axisLabel: { color: '#808080' },
      },
    ],
    series: [
      { name: 'Prompt Tokens', type: 'line', smooth: true, data: [], yAxisIndex: 0 },
      { name: 'Completion Tokens', type: 'line', smooth: true, data: [], yAxisIndex: 0 },
      { name: 'Total', type: 'line', smooth: true, data: [], yAxisIndex: 1, lineStyle: { type: 'dashed' } },
    ],
  })

  resizeObserver = new ResizeObserver(() => chart?.resize())
  resizeObserver.observe(chartRef.value)
})

watch(
  () => props.dataPoints,
  (points) => {
    if (!chart || points.length === 0) return
    const xData = points.map((_, i) => `#${i + 1}`)
    chart.setOption({
      xAxis: { data: xData },
      series: [
        { data: points.map((p) => p.prompt_tokens) },
        { data: points.map((p) => p.completion_tokens) },
        { data: points.map((p) => p.total_tokens) },
      ],
    })
  },
  { deep: true }
)

onUnmounted(() => {
  resizeObserver?.disconnect()
  if (chart) {
    chart.dispose()
    chart = null
  }
})
</script>

<style scoped>
.chart-wrapper {
  width: 100%;
  height: 35vh;
  background: #0f0f1a;
  border-radius: 4px;
  overflow: hidden;
}
.chart-empty {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 100%;
}
.chart-container { width: 100%; height: 100%; }
.chart-container.hidden { visibility: hidden; height: 0; }
</style>
