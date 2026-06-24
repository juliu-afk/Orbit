<!-- BootView.vue: 启动预检视图——挂载时启动轮询，通过后自动跳转 Dashboard -->
<template>
  <BootScreen ref="bootRef" />
</template>

<script setup lang="ts">
import { onMounted, onUnmounted, watch } from 'vue'
import { useRouter } from 'vue-router'
import { usePreFlightStore } from '@/stores/preflight'
import BootScreen from '@/components/common/BootScreen.vue'

const router = useRouter()
const preflight = usePreFlightStore()

onMounted(() => {
  preflight.startPolling()
})

// 通过后自动跳转
watch(
  () => preflight.status,
  (s) => {
    if (s === 'passed') {
      setTimeout(() => router.push({ name: 'dashboard' }), 600)
    }
  }
)

onUnmounted(() => {
  preflight.stopPolling()
})
</script>
