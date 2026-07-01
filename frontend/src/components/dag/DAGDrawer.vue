<script setup lang="ts">
import DagCanvas from '@/components/dag/DagCanvas.vue'
const props = defineProps<{ show: boolean }>()
const emit = defineEmits<{ (e: 'update:show', val: boolean): void }>()
</script>
<template>
<el-drawer :model-value="props.show" title="DAG" direction="rtl" size="600px" @update:model-value="emit('update:show', $event as boolean)"><DagCanvas /></el-drawer>
</template>
