<script setup lang="ts">
// WHY Step 10: Tailwind CSS 从 App.vue 导入而非 main.ts
// ——避免 EDU 插件回退 main.ts 的 import
import './style.css'
</script>

<template>
  <router-view />
</template>
