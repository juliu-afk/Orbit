<script setup lang="ts">
import { ref } from 'vue'
import { useShellStore } from '@/stores/shell'
import SettingsDialog from '@/components/layout/SettingsDialog.vue'

const shell = useShellStore()
const showSettings = ref(false)

// WHY sendBeacon: @tauri-apps/api 在从 http://127.0.0.1:18888 加载时不可用，
// 改用后端 API 控制窗口（FindWindowW + ShowWindow / taskkill）
function minimize() { navigator.sendBeacon('/api/v1/app/minimize', '') }
function toggleMaximize() { navigator.sendBeacon('/api/v1/app/maximize', '') }
function closeWindow() { navigator.sendBeacon('/api/v1/app/quit', '') }
</script>

<template>
  <!-- 持久化拖拽区域——Tauri decorations(false) 无原生标题栏 -->
  <div class="orbit-app-shell">
    <div class="orbit-titlebar">
      <div class="titlebar-left">
        <span class="titlebar-text">Orbit</span>
      </div>
      <div class="titlebar-center"></div>
      <div class="titlebar-controls">
        <button class="tb-btn" @click="shell.toggleFileTree()" title="File tree (Ctrl+B)">📁</button>
        <button class="tb-btn" @click="showSettings = true" title="Settings">⚙</button>
        <button class="tb-btn" @click="minimize()" title="Minimize">─</button>
        <button class="tb-btn" @click="toggleMaximize()" title="Maximize">☐</button>
        <button class="tb-btn tb-close" @click="closeWindow()" title="Close">✕</button>
      </div>
    </div>
    <div class="orbit-content">
      <router-view />
    </div>
    <SettingsDialog v-model:show="showSettings" />
  </div>
</template>

<style>
/* 全局——确保 app shell 撑满窗口 */
html, body, #app { margin: 0; padding: 0; height: 100%; overflow: hidden; }
.orbit-app-shell { display: flex; flex-direction: column; height: 100%; }
.orbit-titlebar {
  height: 32px; min-height: 32px;
  display: flex; align-items: center;
  background: var(--color-orbit-glass); backdrop-filter: blur(var(--glass-blur, 4px));
  border-bottom: 1px solid var(--color-orbit-border, #2a2a4a);
  user-select: none; cursor: grab;
  -webkit-app-region: drag; /* WHY: Tauri frameless 拖拽——比 data-tauri-drag-region 更可靠 */
}
.orbit-titlebar:active { cursor: grabbing; }
.titlebar-left {
  display: flex; align-items: center; padding-left: 12px;
  min-width: 120px; /* WHY: 左侧固定宽度，center 自动填满做拖拽区 */
}
.titlebar-text {
  font-size: 12px; font-weight: 500;
  color: var(--color-orbit-dim, #888);
  font-family: var(--font-mono, monospace);
  pointer-events: none; /* WHY: 穿透点击事件到 data-tauri-drag-region，使标题栏可拖拽 */
}
.titlebar-center { flex: 1; height: 100%; }
.titlebar-controls {
  display: flex; align-items: center; gap: 2px;
  padding-right: 4px;
  -webkit-app-region: no-drag; /* WHY: 按钮区域不触发拖拽 */
}
.tb-btn {
  width: 32px; height: 24px; display: flex; align-items: center; justify-content: center;
  background: transparent; border: none; border-radius: 3px;
  color: var(--color-orbit-text-secondary); font-size: 13px; cursor: pointer;
  font-family: var(--font-mono, monospace);
}
.tb-btn:hover { background: rgba(255,255,255,0.08); color: var(--color-orbit-text); }
.tb-close:hover { background: #e81123; color: #fff; }
.orbit-content { flex: 1; overflow: hidden; }
</style>
