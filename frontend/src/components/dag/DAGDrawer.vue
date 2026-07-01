<script setup lang="ts">
// WHY 新建：DAG 图浮层——包裹 DagCanvas.vue（逻辑不动），el-drawer 作容器。
// v-model 双向绑定 show 状态。
import DagCanvas from '@/components/dag/DagCanvas.vue'

defineProps<{
  show: boolean
}>()

const emit = defineEmits<{
  (e: 'update:show', val: boolean): void
}>()
</script>

<template>
  <el-drawer
    :model-value="show"
    title="DAG 任务图"
    direction="rtl"
    size="600px"
    @update:model-value="emit('update:show', $event as boolean)"
  >
    <DagCanvas />
  </el-drawer>
</template>
