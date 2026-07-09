<!-- TitleBar.vue: frameless 窗口顶部标题栏——可拖拽 + ─□✕ 按钮 -->
<template>
  <div class="titlebar" data-tauri-drag-region>
    <span class="titlebar-title">Orbit</span>
    <div class="titlebar-controls">
      <button class="titlebar-btn" @click="winMinimize" title="最小化">─</button>
      <button class="titlebar-btn" @click="winMaximize" title="最大化">□</button>
      <button class="titlebar-btn titlebar-btn--close" @click="winClose" title="关闭">✕</button>
    </div>
  </div>
</template>

<script setup lang="ts">
function winMinimize() { navigator.sendBeacon('/api/v1/app/minimize', '') }
function winMaximize() { navigator.sendBeacon('/api/v1/app/maximize', '') }
function winClose()    { navigator.sendBeacon('/api/v1/app/quit', '') }
</script>

<style scoped>
.titlebar {
  display: flex; align-items: center; justify-content: space-between;
  height: 32px; padding: 0 8px;
  background: rgba(10,10,20,0.95);
  flex-shrink: 0;
  user-select: none;
}
.titlebar-title {
  font-family: var(--font-mono);
  font-size: 12px; font-weight: 600;
  color: var(--color-orbit-text-secondary);
  letter-spacing: 2px;
}
.titlebar-controls {
  display: flex; gap: 0;
  -webkit-app-region: no-drag;
}
.titlebar-btn {
  display: flex; align-items: center; justify-content: center;
  width: 36px; height: 32px;
  background: none; border: none;
  color: var(--color-orbit-text-secondary);
  font-family: var(--font-mono); font-size: 13px;
  cursor: pointer;
  transition: background 0.15s, color 0.15s;
}
.titlebar-btn:hover { background: rgba(255,255,255,0.08); color: #fff; }
.titlebar-btn--close:hover { background: #f44336; color: #fff; }
</style>
