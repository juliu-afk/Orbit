<script setup lang="ts">
import { ref } from 'vue'
import { watch } from 'vue'
import { useSettingsStore } from '@/stores/settings'
import { useShellStore } from '@/stores/shell'
const props = defineProps<{ show: boolean }>()
const emit = defineEmits<{ (e: 'update:show', v: boolean): void }>()
const s = useSettingsStore()
const shell = useShellStore()
// UX-7: Agent 模型选择 + 快捷键参考
const agentModel = ref(localStorage.getItem('orbit-agent-model') || 'deepseek-v4-pro')
watch(agentModel, (v) => localStorage.setItem('orbit-agent-model', v))
const shortcuts = [
  { key: 'Ctrl+B', desc: 'Toggle file tree' },
  { key: 'Ctrl+/', desc: 'Toggle command palette' },
  { key: 'Ctrl+K', desc: 'Focus search' },
  { key: 'Esc', desc: 'Close panel' },
  { key: '←↑↓→', desc: 'Navigate history' },
]
// v0.24: 布局预设一键切换——改宽度+显隐，避免零宽DOM残留
function preset(name: string) {
  switch (name) {
    case 'default': s.fileTreeLeft = true; s.agentRight = true; s.fileTreeWidth = 240; s.rightPanelWidth = 260; shell.showFileTree = true; break  // P1 fix
    case 'wide': s.fileTreeLeft = false; s.agentRight = true; s.fileTreeWidth = 0; s.rightPanelWidth = 260; shell.showFileTree = false; break     // P1 fix
    case 'focus': s.fileTreeLeft = true; s.agentRight = false; s.fileTreeWidth = 240; s.rightPanelWidth = 0; shell.closeFileReview(); break       // P1 fix: 收起右面板
  }
}
</script>
<template>
<el-dialog :model-value="props.show" title="Settings" width="400px" @update:model-value="emit('update:show',$event as boolean)">
<div style="font-family:var(--font-mono);font-size:12px;color:var(--color-orbit-text)">
<div class="sg"><div class="sl">Theme</div><div class="flex gap-2"><button class="tb" :class="{active:s.theme==='dark'}" @click="s.theme='dark'">Dark</button><button class="tb" :class="{active:s.theme==='light'}" @click="s.theme='light'">Light</button></div></div>
<div class="sg"><div class="sl">Transparency</div><div class="sr"><span class="sw">Opacity</span><input type="range" min="15" max="100" :value="s.glassOpacity" @input="s.glassOpacity=+($event.target as HTMLInputElement).value" class="slider"/><span class="sv">{{s.glassOpacity}}%</span></div><div class="sr"><span class="sw">Blur</span><input type="range" min="0" max="20" :value="s.glassBlur" @input="s.glassBlur=+($event.target as HTMLInputElement).value" class="slider"/><span class="sv">{{s.glassBlur}}px</span></div></div>
<div class="sg"><div class="sl">Presets</div><div class="flex gap-2"><button class="tb" @click="preset('default')">Default</button><button class="tb" @click="preset('wide')">Wide</button><button class="tb" @click="preset('focus')">Focus</button></div></div>
<div class="sg"><div class="sl">Layout</div><div class="sr"><span class="sw">File tree</span><button class="lb" :class="{active:s.fileTreeLeft}" @click="s.fileTreeLeft=true">Left</button><button class="lb" :class="{active:!s.fileTreeLeft}" @click="s.fileTreeLeft=false">Right</button></div><div class="sr"><span class="sw">Agent</span><button class="lb" :class="{active:s.agentRight}" @click="s.agentRight=true">Right</button><button class="lb" :class="{active:!s.agentRight}" @click="s.agentRight=false">Left</button></div></div>
<div class="sg"><div class="sl">Width</div><div class="sr"><span class="sw">File tree</span><input type="range" min="160" max="480" :value="s.fileTreeWidth" @input="s.fileTreeWidth=+($event.target as HTMLInputElement).value" class="slider"/><span class="sv">{{s.fileTreeWidth}}px</span></div><div class="sr"><span class="sw">Right</span><input type="range" min="180" max="600" :value="s.rightPanelWidth" @input="s.rightPanelWidth=+($event.target as HTMLInputElement).value" class="slider"/><span class="sv">{{s.rightPanelWidth}}px</span></div></div>
<!-- UX-7: Agent 模型配置 -->
	<div class="sg"><div class="sl">Agent Model</div>
	  <select class="ms" :value="agentModel" @change="agentModel=($event.target as HTMLSelectElement).value">
	    <option value="deepseek-v4-pro">DeepSeek V4 Pro (recommended)</option>
	    <option value="deepseek-v4-flash">DeepSeek V4 Flash (fast)</option>
	    <option value="glm-5.2">GLM-5.2 (backup)</option>
	  </select>
	</div>
	<!-- UX-7: 快捷键参考 -->
	<div class="sg"><div class="sl">Keyboard Shortcuts</div>
	  <div class="kbd-grid">
	    <div v-for="kb in shortcuts" :key="kb.key" class="kbd-row"><kbd>{{ kb.key }}</kbd><span>{{ kb.desc }}</span></div>
	  </div>
	</div>
	<div class="mt-4 pt-3" style="border-top:1px solid var(--color-orbit-border)"><button class="rb" @click="s.resetDefaults()">Reset</button></div>
</div></el-dialog></template>
<style scoped>.sg{margin-bottom:14px}.sl{font-size:11px;color:var(--color-orbit-accent);margin-bottom:6px;text-transform:uppercase;letter-spacing:.5px}.sr{display:flex;align-items:center;gap:8px;margin-bottom:4px}.sw{color:var(--color-orbit-text-secondary);width:80px}.sv{width:40px;text-align:right;font-size:10px;color:var(--color-orbit-text-muted)}.slider{flex:1;accent-color:var(--color-orbit-accent);height:4px}.tb,.lb{font-family:var(--font-mono);font-size:11px;padding:4px 12px;border-radius:4px;background:var(--color-orbit-surface);border:1px solid var(--color-orbit-border);color:var(--color-orbit-text-secondary);cursor:pointer}.tb.active,.lb.active{background:var(--color-orbit-accent-dim);border-color:var(--color-orbit-accent);color:var(--color-orbit-accent)}.rb{font-family:var(--font-mono);font-size:11px;padding:4px 12px;border-radius:4px;background:transparent;border:1px solid var(--color-orbit-error);color:var(--color-orbit-error);cursor:pointer}.rb:hover{background:rgba(244,67,54,.1)}
.ms{width:100%;padding:6px 8px;border-radius:4px;background:var(--color-orbit-surface);border:1px solid var(--color-orbit-border);color:var(--color-orbit-text);font-size:11px;font-family:var(--font-mono)}.kbd-grid{display:flex;flex-direction:column;gap:3px}.kbd-row{display:flex;align-items:center;gap:8px;font-size:11px}.kbd-row span{color:var(--color-orbit-text-secondary)}kbd{padding:1px 6px;border-radius:3px;background:var(--color-orbit-surface);border:1px solid var(--color-orbit-border);font-size:10px;font-family:var(--font-mono)}</style>
