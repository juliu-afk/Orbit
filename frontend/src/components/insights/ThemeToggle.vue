<!-- 主题切换 (Phase 3.5) -->
<template>
  <el-button size="small" @click="toggle" :icon="isDark ? 'Sunny' : 'Moon'">
    {{ isDark ? 'Light' : 'Dark' }}
  </el-button>
</template>

<script setup lang="ts">
import { ref } from 'vue'
const isDark = ref(document.documentElement.classList.contains('dark'))
function toggle() {
  isDark.value = !isDark.value
  document.documentElement.classList.toggle('dark', isDark.value)
  localStorage.setItem('theme', isDark.value ? 'dark' : 'light')
}
</script>
