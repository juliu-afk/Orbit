<script setup lang="ts">
// WHY v0.23: 统一设置面板——主题/透明度/布局，el-dialog 容器，与现有对话框风格一致
import { useSettingsStore } from '@/stores/settings'

const props = defineProps<{ show: boolean }>()
const emit = defineEmits<{ (e: 'update:show', v: boolean): void }>()

const s = useSettingsStore()
</script>

<template>
<el-dialog :model-value="props.show" title="Settings" width="400px" @update:model-value="emit('update:show', $event as boolean)">
  <div style="font-family:var(--font-mono);font-size:12px;color:var(--color-orbit-text)">

    <!-- 主题 -->
    <div class="setting-group">
      <div class="setting-label">Theme</div>
      <div class="flex gap-2">
        <button class="theme-btn" :class="{ active: s.theme === 'dark' }" @click="s.theme = 'dark'"> Dark</button>
        <button class="theme-btn" :class="{ active: s.theme === 'light' }" @click="s.theme = 'light'"> Light</button>
      </div>
    </div>

    <!-- 透明度 -->
    <div class="setting-group">
      <div class="setting-label">Transparency</div>
      <div class="setting-row">
        <span style="color:var(--color-orbit-text-secondary);width:80px">Opacity</span>
        <input type="range" min="50" max="95" :value="s.glassOpacity" @input="s.glassOpacity = +($event.target as HTMLInputElement).value" class="slider" />
        <span class="setting-val">{{ s.glassOpacity }}%</span>
      </div>
      <div class="setting-row">
        <span style="color:var(--color-orbit-text-secondary);width:80px">Blur</span>
        <input type="range" min="0" max="24" :value="s.glassBlur" @input="s.glassBlur = +($event.target as HTMLInputElement).value" class="slider" />
        <span class="setting-val">{{ s.glassBlur }}px</span>
      </div>
    </div>

    <!-- 布局 -->
    <div class="setting-group">
      <div class="setting-label">Layout</div>
      <div class="setting-row">
        <span style="color:var(--color-orbit-text-secondary);width:80px">File tree</span>
        <button class="layout-btn" :class="{ active: s.fileTreeLeft }" @click="s.fileTreeLeft = true">Left</button>
        <button class="layout-btn" :class="{ active: !s.fileTreeLeft }" @click="s.fileTreeLeft = false">Right</button>
      </div>
      <div class="setting-row">
        <span style="color:var(--color-orbit-text-secondary);width:80px">Agent panel</span>
        <button class="layout-btn" :class="{ active: s.agentRight }" @click="s.agentRight = true">Right</button>
        <button class="layout-btn" :class="{ active: !s.agentRight }" @click="s.agentRight = false">Left</button>
      </div>
    </div>

    <!-- 面板宽度 -->
    <div class="setting-group">
      <div class="setting-label">Panel Width</div>
      <div class="setting-row">
        <span style="color:var(--color-orbit-text-secondary);width:80px">File tree</span>
        <input type="range" min="160" max="480" :value="s.fileTreeWidth" @input="s.fileTreeWidth = +($event.target as HTMLInputElement).value" class="slider" />
        <span class="setting-val">{{ s.fileTreeWidth }}px</span>
      </div>
      <div class="setting-row">
        <span style="color:var(--color-orbit-text-secondary);width:80px">Right panel</span>
        <input type="range" min="180" max="600" :value="s.rightPanelWidth" @input="s.rightPanelWidth = +($event.target as HTMLInputElement).value" class="slider" />
        <span class="setting-val">{{ s.rightPanelWidth }}px</span>
      </div>
    </div>

    <!-- Reset -->
    <div class="mt-4 pt-3" style="border-top:1px solid var(--color-orbit-border)">
      <button class="reset-btn" @click="s.resetDefaults()">Reset Defaults</button>
    </div>

  </div>
</el-dialog>
</template>

<style scoped>
.setting-group { margin-bottom: 14px; }
.setting-label { font-size: 11px; color: var(--color-orbit-accent); margin-bottom: 6px; text-transform: uppercase; letter-spacing: 0.5px; }
.setting-row { display: flex; align-items: center; gap: 8px; margin-bottom: 4px; }
.setting-val { width: 40px; text-align: right; font-size: 10px; color: var(--color-orbit-text-muted); }
.slider { flex: 1; accent-color: var(--color-orbit-accent); height: 4px; }
.theme-btn, .layout-btn {
  font-family: var(--font-mono); font-size: 11px; padding: 4px 12px; border-radius: 4px;
  background: var(--color-orbit-surface); border: 1px solid var(--color-orbit-border);
  color: var(--color-orbit-text-secondary); cursor: pointer;
}
.theme-btn.active, .layout-btn.active {
  background: var(--color-orbit-accent-dim); border-color: var(--color-orbit-accent); color: var(--color-orbit-accent);
}
.reset-btn {
  font-family: var(--font-mono); font-size: 11px; padding: 4px 12px; border-radius: 4px;
  background: transparent; border: 1px solid var(--color-orbit-error);
  color: var(--color-orbit-error); cursor: pointer;
}
.reset-btn:hover { background: rgba(244,67,54,0.1); }
</style>
