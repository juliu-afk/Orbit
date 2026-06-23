<!-- 指标统计卡片：标题 + 数值 + 单位 + 趋势箭头 -->
<template>
  <div class="metrics-card" :class="{ 'metrics-card--loading': loading }">
    <div class="metrics-card__title">{{ title }}</div>
    <div class="metrics-card__value">
      <span v-if="loading || value === null">---</span>
      <span v-else>{{ formattedValue }}</span>
      <span v-if="!loading && value !== null" class="metrics-card__unit">{{ unit }}</span>
    </div>
    <div v-if="trend !== undefined && !loading" class="metrics-card__trend" :class="trendClass">
      {{ trend >= 0 ? '↑' : '↓' }} {{ Math.abs(trend) }}%
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'

const props = withDefaults(defineProps<{
  title: string
  value: number | null
  unit?: string
  trend?: number
  loading?: boolean
}>(), {
  unit: '',
  loading: false,
})

const formattedValue = computed(() => {
  if (props.value === null) return '---'
  if (props.value >= 1000) return props.value.toLocaleString()
  return String(props.value)
})

const trendClass = computed(() => ({
  'metrics-card__trend--up': (props.trend ?? 0) > 0,
  'metrics-card__trend--down': (props.trend ?? 0) < 0,
}))
</script>

<style scoped>
.metrics-card {
  background: #16163a;
  border: 1px solid #2a2a5a;
  border-radius: 8px;
  padding: 16px;
  min-width: 140px;
  text-align: center;
}
.metrics-card--loading { opacity: 0.5; }
.metrics-card__title {
  font-size: 12px;
  color: #8888aa;
  margin-bottom: 8px;
}
.metrics-card__value {
  font-size: 28px;
  font-weight: 700;
  color: #ffffff;
}
.metrics-card__unit {
  font-size: 12px;
  color: #6666aa;
  margin-left: 4px;
}
.metrics-card__trend {
  font-size: 12px;
  margin-top: 4px;
}
.metrics-card__trend--up { color: #4caf50; }
.metrics-card__trend--down { color: #f44336; }
</style>
