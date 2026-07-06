<!-- UX-4: 非阻塞连接提示——顶部 banner 替代全屏遮罩 -->
<template>
  <div v-if="visible" class="conn-banner">
    <span class="conn-icon">⚠️</span>
    <span class="conn-text">连接已断开</span>
    <span class="conn-retry" v-if="countdown > 0">— {{ countdown }}s 后自动重连</span>
    <button class="conn-btn" @click="$emit('reconnect')">手动重连</button>
  </div>
</template>

<script setup lang="ts">
import { ref, watch, onBeforeUnmount } from 'vue'

const props = defineProps<{ visible: boolean }>()
const emit = defineEmits<{ reconnect: [] }>()

const countdown = ref(0)
let _timer: ReturnType<typeof setInterval> | null = null

watch(() => props.visible, (v) => {
  if (v) { countdown.value = 30; _timer = setInterval(() => { countdown.value--; if (countdown.value <= 0 && _timer) { clearInterval(_timer); _timer = null; emit('reconnect') } }, 1000) }
  else { countdown.value = 0; if (_timer) { clearInterval(_timer); _timer = null } }
})

onBeforeUnmount(() => { if (_timer) clearInterval(_timer) })
</script>

<style scoped>
.conn-banner {
  position: fixed; top: 0; left: 0; right: 0; z-index: 9998;
  display: flex; align-items: center; gap: 8px; padding: 6px 16px;
  background: #3a2a0a; border-bottom: 1px solid var(--color-orbit-warn, #d2991d);
  font-size: 12px; color: var(--color-orbit-warn, #d2991d);
  font-family: var(--font-mono); backdrop-filter: blur(8px);
}
.conn-icon { font-size: 14px }
.conn-text { flex: 1 }
.conn-retry { color: var(--color-orbit-text-secondary) }
.conn-btn {
  padding: 2px 12px; border: 1px solid var(--color-orbit-warn, #d2991d); border-radius: 4px;
  background: transparent; color: var(--color-orbit-warn); cursor: pointer; font-size: 11px;
}
.conn-btn:hover { background: rgba(210, 153, 29, 0.15) }
</style>
