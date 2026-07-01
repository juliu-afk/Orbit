<script setup lang="ts">
// WHY 新建：终端风格输入框——$ 提示符 + 等宽字体 + 闪烁光标 + slash 命令补全 + 历史导航。
// 替代旧 el-input + 按钮的 web 表单交互。
import { ref, computed } from 'vue'

const emit = defineEmits<{
  (e: 'send', text: string): void
  (e: 'navigate-history', direction: -1 | 1): void
}>()

const inputRef = ref<HTMLTextAreaElement | null>(null)
const inputText = ref('')

// Slash 命令列表
const SLASH_COMMANDS = ['/task', '/review', '/dream', '/search', '/help', '/compose']
const showAutocomplete = ref(false)
const autocompleteIndex = ref(0)

const filteredCommands = computed(() => {
  if (!inputText.value.startsWith('/') || inputText.value.includes(' ')) return []
  return SLASH_COMMANDS.filter(c => c.startsWith(inputText.value))
})

function onKeydown(e: KeyboardEvent) {
  // Enter 发送
  if (e.key === 'Enter' && !e.shiftKey) {
    if (showAutocomplete.value && filteredCommands.value.length > 0) {
      // Tab 补全优先
      e.preventDefault()
      inputText.value = filteredCommands.value[autocompleteIndex.value]
      showAutocomplete.value = false
      return
    }
    e.preventDefault()
    const text = inputText.value.trim()
    if (text) {
      emit('send', text)
      inputText.value = ''
      showAutocomplete.value = false
      autocompleteIndex.value = 0
    }
  }

  // Shift+Enter 换行
  if (e.key === 'Enter' && e.shiftKey) {
    return // 允许默认换行行为
  }

  // Tab 补全
  if (e.key === 'Tab') {
    e.preventDefault()
    if (filteredCommands.value.length > 0) {
      if (!showAutocomplete.value) {
        showAutocomplete.value = true
        autocompleteIndex.value = 0
      } else {
        autocompleteIndex.value = (autocompleteIndex.value + 1) % filteredCommands.value.length
      }
    }
  }

  // ↑↓ 历史导航（在空行或行首时）
  if (e.key === 'ArrowUp' && inputText.value === '') {
    e.preventDefault()
    emit('navigate-history', -1)
  }
  if (e.key === 'ArrowDown' && inputText.value === '') {
    e.preventDefault()
    emit('navigate-history', 1)
  }

  // Esc 关闭自动补全
  if (e.key === 'Escape') {
    showAutocomplete.value = false
  }
}

function onInput() {
  if (inputText.value.startsWith('/') && !inputText.value.includes(' ')) {
    showAutocomplete.value = filteredCommands.value.length > 0
  } else {
    showAutocomplete.value = false
  }
}

function focus() {
  inputRef.value?.focus()
}

defineExpose({ focus })
</script>

<template>
  <div class="input-box">
    <!-- Slash 命令补全提示 -->
    <div
      v-if="showAutocomplete && filteredCommands.length > 0"
      class="autocomplete-popup mx-3 mb-1 rounded px-2 py-1 text-xs"
      style="background: var(--color-orbit-surface); font-family: var(--font-mono);"
    >
      <div
        v-for="(cmd, idx) in filteredCommands"
        :key="cmd"
        :class="{ 'autocomplete-active': idx === autocompleteIndex }"
        class="autocomplete-item px-1 py-0.5 rounded cursor-pointer"
      >
        {{ cmd }}
      </div>
    </div>

    <!-- 输入行 -->
    <div class="input-row flex items-start gap-2 px-3 py-2">
      <span
        class="prompt shrink-0 select-none"
        style="color: var(--color-orbit-accent); font-family: var(--font-mono); font-size: 14px;"
      >
        $
      </span>
      <textarea
        ref="inputRef"
        v-model="inputText"
        class="terminal-input flex-1 resize-none outline-none"
        style="
          background: transparent;
          border: none;
          color: var(--color-orbit-text);
          font-family: var(--font-mono);
          font-size: 13px;
          line-height: 1.6;
          caret-color: var(--color-orbit-accent);
        "
        rows="1"
        placeholder="输入消息或 / 查看命令..."
        @keydown="onKeydown"
        @input="onInput"
      />
    </div>
  </div>
</template>

<style scoped>
.terminal-input::placeholder {
  color: var(--color-orbit-text-muted);
}
.autocomplete-item {
  color: var(--color-orbit-text-secondary);
}
.autocomplete-item.autocomplete-active {
  color: var(--color-orbit-accent);
  background: rgba(76, 175, 80, 0.1);
}
</style>
