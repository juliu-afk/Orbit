<script setup lang="ts">
import { ref } from 'vue'
import TokenChart from '@/components/charts/TokenChart.vue'
import type { TokenPoint } from '@/types/dashboard'
const props = defineProps<{ show: boolean }>()
const emit = defineEmits<{ (e: 'update:show', val: boolean): void }>()
const points = ref<TokenPoint[]>([])
</script>
<template>
<el-drawer :model-value="props.show" title="Tokens" direction="rtl" size="480px" @update:model-value="emit('update:show', $event as boolean)"><TokenChart :data-points="points" /></el-drawer>
</template>
