<template>
  <!-- 持久化拖拽区域——Tauri decorations(false) 无原生标题栏 -->
  <div class="orbit-app-shell">
    <div class="orbit-titlebar" data-tauri-drag-region>
      <span class="titlebar-text">Orbit</span>
    </div>
    <div class="orbit-content">
      <router-view />
    </div>
  </div>
</template>

<style>
/* 全局——确保 app shell 撑满窗口 */
html, body, #app { margin: 0; padding: 0; height: 100%; overflow: hidden; }
.orbit-app-shell { display: flex; flex-direction: column; height: 100%; }
.orbit-titlebar {
  height: 32px; min-height: 32px;
  display: flex; align-items: center; justify-content: center;
  background: var(--color-orbit-surface, #1a1a2e);
  border-bottom: 1px solid var(--color-orbit-border, #2a2a4a);
  user-select: none; cursor: default;
}
.titlebar-text {
  font-size: 12px; font-weight: 500;
  color: var(--color-orbit-dim, #888);
  font-family: var(--font-mono, monospace);
}
.orbit-content { flex: 1; overflow: hidden; }
</style>
