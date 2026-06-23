<!-- 断线遮罩：重连 5 次失败后显示 -->
<template>
  <div class="overlay-mask">
    <div class="overlay-content">
      <el-icon :size="48" color="#F56C6C"><warning-filled /></el-icon>
      <h3>连接已断开</h3>
      <p>无法连接到 Orbit 服务，请检查后端是否启动。</p>
      <el-button type="primary" @click="$emit('reconnect')">手动重连</el-button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { WarningFilled } from '@element-plus/icons-vue'

defineEmits<{
  reconnect: []
}>()
</script>

<style scoped>
.overlay-mask {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.6);
  display: flex;
  justify-content: center;
  align-items: center;
  z-index: 9999;
}
.overlay-content {
  text-align: center;
  color: #fff;
  padding: 40px;
  background: #1a1a2e;
  border-radius: 8px;
}
.overlay-content h3 { margin: 16px 0 8px; }
.overlay-content p { margin-bottom: 24px; color: #a0a0a0; }
</style>
