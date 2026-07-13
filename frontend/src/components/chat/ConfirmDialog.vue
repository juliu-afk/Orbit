<script setup lang="ts">
import { ref, watch } from 'vue'

interface ConfirmRequest {
  id: string
  tool_name: string
  tool_args: Record<string, unknown>
  message: string
  allow_remember: boolean
}

const props = defineProps<{ request: ConfirmRequest | null }>()
const emit = defineEmits<{
  (e: 'respond', response: { id: string; approved: boolean; remember: boolean }): void
}>()

const remember = ref(false)
const visible = ref(false)
const timeoutRef = ref<ReturnType<typeof setTimeout> | null>(null)

watch(() => props.request, (req) => {
  if (req) {
    visible.value = true
    remember.value = false
    if (timeoutRef.value) clearTimeout(timeoutRef.value)
    timeoutRef.value = setTimeout(() => {
      emit('respond', { id: req.id, approved: false, remember: false })
      visible.value = false
    }, 5000)
  }
})

function onApprove() {
  if (timeoutRef.value) clearTimeout(timeoutRef.value)
  if (props.request) emit('respond', { id: props.request.id, approved: true, remember: remember.value })
  visible.value = false
}

function onDeny() {
  if (timeoutRef.value) clearTimeout(timeoutRef.value)
  if (props.request) emit('respond', { id: props.request.id, approved: false, remember: false })
  visible.value = false
}
</script>

<template>
<div v-if="visible && request" class="confirm-overlay" @click.self="onDeny">
  <div class="confirm-dialog" style="font-family:var(--font-mono)">
    <div class="confirm-header">
      <span class="confirm-icon">⚠️</span>
      <span class="confirm-title">确认工具执行</span>
    </div>
    <div class="confirm-body">
      <div class="confirm-tool">{{ request.tool_name }}</div>
      <div class="confirm-msg">{{ request.message }}</div>
      <div v-if="request.allow_remember" class="confirm-remember">
        <label><input type="checkbox" v-model="remember" /><span>本会话记住</span></label>
      </div>
    </div>
    <div class="confirm-footer">
      <button class="confirm-btn deny" @click="onDeny">拒绝</button>
      <button class="confirm-btn approve" @click="onApprove">允许</button>
    </div>
  </div>
</div>
</template>

<style scoped>
.confirm-overlay{position:fixed;inset:0;z-index:9999;display:flex;align-items:center;justify-content:center;background:rgba(0,0,0,0.4)}
.confirm-dialog{background:var(--color-orbit-surface);border:1px solid var(--color-orbit-accent);border-radius:8px;padding:16px;min-width:320px;max-width:480px;box-shadow:0 4px 24px rgba(0,0,0,0.3)}
.confirm-header{display:flex;align-items:center;gap:8px;margin-bottom:12px}
.confirm-icon{font-size:18px}
.confirm-title{font-size:13px;font-weight:600;color:var(--color-orbit-warn)}
.confirm-body{margin-bottom:14px}
.confirm-tool{font-size:11px;color:var(--color-orbit-accent);margin-bottom:6px}
.confirm-msg{font-size:12px;color:var(--color-orbit-text-secondary);line-height:1.5}
.confirm-remember{margin-top:8px;font-size:11px;color:var(--color-orbit-text-secondary)}
.confirm-remember label{display:flex;align-items:center;gap:6px;cursor:pointer}
.confirm-footer{display:flex;gap:8px;justify-content:flex-end}
.confirm-btn{padding:4px 14px;border:none;border-radius:4px;cursor:pointer;font-size:12px;font-family:var(--font-mono)}
.confirm-btn.approve{background:var(--color-orbit-accent);color:#fff}
.confirm-btn.deny{background:transparent;border:1px solid var(--color-orbit-border);color:var(--color-orbit-text-secondary)}
.confirm-btn.deny:hover{background:var(--color-orbit-surface-hover)}
</style>
