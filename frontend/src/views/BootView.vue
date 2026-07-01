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

// 通过后自动跳转；降级(sandbox等非关键失败)也允许进入
watch(
  () => preflight.status,
  (s) => {
    if (s === 'passed' || s === 'failed') {
      // 检查关键探针——env/db/agent 全部通过即可进入
      const critical = preflight.checks.filter(
        c => ['environment', 'database', 'agent'].includes(c.name)
      )
      const allCriticalOk = critical.length > 0 && critical.every(
        c => c.status === 'passed' || c.status === 'repaired'
      )
      if (s === 'passed' || allCriticalOk) {
        setTimeout(() => router.push({ name: 'app' }), 600)
      }
    }
  }
)

onUnmounted(() => {
  preflight.stopPolling()
})
</script>
