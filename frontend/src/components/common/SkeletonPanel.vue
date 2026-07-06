<!-- UX-6: 骨架屏——面板加载时显示而非空白 -->
<template>
  <div class="skeleton-panel" :style="{ height }">
    <div v-for="i in lines" :key="i" class="sk-line" :style="{ width: randomWidth(i), animationDelay: `${i * 0.1}s` }" />
  </div>
</template>

<script setup lang="ts">
// UX-6: 简单确定性宽度——避免每次渲染随机宽度不同
const WIDTHS = ['92%','78%','85%','63%','71%','88%','55%','94%']
withDefaults(defineProps<{ lines?: number; height?: string }>(), { lines: 5, height: '100%' })
function randomWidth(i: number): string { return WIDTHS[i % WIDTHS.length] }
</script>

<style scoped>
.skeleton-panel { display:flex;flex-direction:column;gap:8px;padding:16px;overflow:hidden }
.sk-line { height:12px;border-radius:3px;background:linear-gradient(90deg, var(--color-orbit-border) 25%, var(--color-orbit-surface-hover) 50%, var(--color-orbit-border) 75%); background-size:200% 100%; animation:sk-shimmer 1.5s ease-in-out infinite }
@keyframes sk-shimmer { 0% { background-position: 200% 0 } 100% { background-position: -200% 0 } }
</style>
