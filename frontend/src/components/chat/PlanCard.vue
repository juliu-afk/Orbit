<!-- UX-8: Agent 计划卡片——执行前展示步骤列表，Approve/Skip/Modify -->
<template>
  <div v-if="visible" class="plan-card">
    <div class="plan-header">
      <span class="plan-icon">📋</span>
      <span class="plan-title">Agent Plan</span>
      <span class="plan-meta">{{ steps.length }} steps</span>
    </div>
    <div class="plan-steps">
      <div v-for="(s, i) in steps" :key="i" class="plan-step" :class="{ done: s.status === 'done', active: s.status === 'active' }">
        <span class="step-num">{{ s.status === 'done' ? '✓' : i + 1 }}</span>
        <span class="step-desc">{{ s.description }}</span>
      </div>
    </div>
    <div class="plan-actions">
      <button class="plan-btn plan-btn--go" @click="$emit('approve')">▶ Approve</button>
      <button class="plan-btn" @click="$emit('skip')">⏭ Skip</button>
      <button class="plan-btn plan-btn--mod" @click="$emit('modify')">✏️ Modify</button>
    </div>
  </div>
</template>

<script setup lang="ts">
export interface PlanStep { description: string; status: 'pending' | 'active' | 'done' }

defineProps<{ visible: boolean; steps: PlanStep[] }>()
defineEmits<{ approve: []; skip: []; modify: [] }>()
</script>

<style scoped>
.plan-card { margin:8px 12px;border:1px solid var(--color-orbit-accent);border-radius:6px;background:var(--color-orbit-glass);overflow:hidden;font-family:var(--font-mono);font-size:12px }
.plan-header { display:flex;align-items:center;gap:8px;padding:8px 12px;background:var(--color-orbit-accent-dim);border-bottom:1px solid var(--color-orbit-border) }
.plan-icon { font-size:14px }.plan-title { font-weight:600;color:var(--color-orbit-accent);flex:1 }.plan-meta { font-size:10px;color:var(--color-orbit-text-secondary) }
.plan-steps { padding:4px 0 }
.plan-step { display:flex;align-items:center;gap:8px;padding:4px 12px;color:var(--color-orbit-text-secondary) }
.plan-step.active { color:var(--color-orbit-text);background:var(--color-orbit-surface-hover) }
.plan-step.done { color:var(--color-orbit-text-muted);text-decoration:line-through }
.step-num { width:18px;height:18px;display:flex;align-items:center;justify-content:center;border-radius:50%;background:var(--color-orbit-surface);font-size:10px;flex-shrink:0 }
.plan-step.active .step-num { background:var(--color-orbit-accent-dim);color:var(--color-orbit-accent) }
.plan-step.done .step-num { background:var(--color-orbit-success-dim, #1a3a1a);color:var(--color-orbit-success,#3fb950) }
.plan-actions { display:flex;gap:4px;padding:8px 12px;border-top:1px solid var(--color-orbit-border) }
.plan-btn { padding:4px 14px;border:1px solid var(--color-orbit-border);border-radius:4px;background:transparent;color:var(--color-orbit-text-secondary);cursor:pointer;font-size:11px;font-family:var(--font-mono) }
.plan-btn:hover { background:var(--color-orbit-surface-hover) }
.plan-btn--go { border-color:var(--color-orbit-accent);color:var(--color-orbit-accent) }
.plan-btn--mod { border-color:var(--color-orbit-warn);color:var(--color-orbit-warn) }
</style>
