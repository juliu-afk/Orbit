<script setup lang="ts">
// WHY 新建：Token 图表浮层——包裹 TokenChart.vue（逻辑不动），el-drawer 作容器。
import { ref } from 'vue'
import TokenChart from '@/components/charts/TokenChart.vue'
import type { TokenPoint } from '@/types/dashboard'

defineProps<{
  show: boolean
}>()

const emit = defineEmits<{
  (e: 'update:show', val: boolean): void
}>()

// WHY 在容器层管理 dataPoints：旧 DashboardView 的 token 数据由 WS token:update 填充。
// 后续 TerminalShell 的 WS handler 会追加到这里。
const points = ref<TokenPoint[]>([])
</script>

<template>
  <el-drawer
    :model-value="show"
    title="Token 消耗图表"
    direction="rtl"
    size="480px"
    @update:model-value="emit('update:show', $event as boolean)"
  >
    <TokenChart :data-points="points" />
  </el-drawer>
</template>
