<script setup lang="ts">
// WHY 新建：全局自定义右键菜单，替代浏览器默认右键菜单。
// Teleport 到 body，点击菜单外部 / Esc / 窗口失焦时关闭。
import { ref, onMounted, onUnmounted } from 'vue'
import type { ChatMessage } from '@/stores/chat'

const props = defineProps<{
  message: ChatMessage
  x: number
  y: number
}>()

const emit = defineEmits<{
  (e: 'close'): void
  (e: 'copy'): void
  (e: 'copy-link'): void
  (e: 'quote'): void
  (e: 'open-file'): void
  (e: 'retry'): void
}>()

const menuRef = ref<HTMLDivElement | null>(null)

// 防止菜单超出窗口
const adjustedX = ref(props.x)
const adjustedY = ref(props.y)

onMounted(() => {
  document.addEventListener('click', onOutsideClick)
  document.addEventListener('keydown', onEsc)

  // 调整位置——菜单不超出窗口边界
  if (menuRef.value) {
    const rect = menuRef.value.getBoundingClientRect()
    if (props.x + rect.width > window.innerWidth) {
      adjustedX.value = props.x - rect.width
    }
    if (props.y + rect.height > window.innerHeight) {
      adjustedY.value = props.y - rect.height
    }
  }
})

onUnmounted(() => {
  document.removeEventListener('click', onOutsideClick)
  document.removeEventListener('keydown', onEsc)
})

function onOutsideClick() {
  emit('close')
}

function onEsc(e: KeyboardEvent) {
  if (e.key === 'Escape') {
    emit('close')
  }
}

function hasFilePath(): boolean {
  // 检测消息文本是否包含文件路径
  return props.message.text.includes('.py') ||
    props.message.text.includes('.ts') ||
    props.message.text.includes('.vue') ||
    props.message.text.includes('/') ||
    props.message.text.includes('\\')
}
</script>

<template>
  <Teleport to="body">
    <div
      ref="menuRef"
      class="context-menu rounded py-1 shadow-lg"
      :style="{
        left: adjustedX + 'px',
        top: adjustedY + 'px',
        background: 'var(--color-orbit-surface)',
        border: '1px solid var(--color-orbit-border)',
        fontFamily: 'var(--font-mono)',
        fontSize: '12px',
        minWidth: '180px',
        zIndex: 10000,
      }"
      @click.stop
    >
      <div
        class="menu-item px-3 py-1.5 cursor-pointer flex items-center gap-2"
        style="color: var(--color-orbit-text);"
        @click="emit('copy')"
      >
        <span>📋</span>
        <span>复制</span>
      </div>

      <div
        class="menu-item px-3 py-1.5 cursor-pointer flex items-center gap-2"
        style="color: var(--color-orbit-text);"
        @click="emit('copy-link')"
      >
        <span>📎</span>
        <span>复制消息链接</span>
      </div>

      <div
        class="menu-item px-3 py-1.5 cursor-pointer flex items-center gap-2"
        style="color: var(--color-orbit-text);"
        @click="emit('quote')"
      >
        <span>💬</span>
        <span>引用这条消息</span>
      </div>

      <div
        v-if="hasFilePath()"
        class="menu-item px-3 py-1.5 cursor-pointer flex items-center gap-2"
        style="color: var(--color-orbit-text);"
        @click="emit('open-file')"
      >
        <span>📁</span>
        <span>打开文件</span>
      </div>

      <div class="menu-separator mx-2 my-1" style="border-top: 1px solid var(--color-orbit-border);" />

      <div
        class="menu-item px-3 py-1.5 cursor-pointer flex items-center gap-2"
        style="color: var(--color-orbit-text);"
        @click="emit('retry')"
      >
        <span>🔄</span>
        <span>重新执行</span>
      </div>
    </div>
  </Teleport>
</template>

<style scoped>
.menu-item:hover {
  background: var(--color-orbit-surface-hover);
}
</style>
