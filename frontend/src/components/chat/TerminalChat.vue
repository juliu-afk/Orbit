<script setup lang="ts">
// WHY 新建：替代 ChatPanel.vue + ChatStream.vue——终端风格聊天容器。
// 消息列表渲染 + SSE 流式追加 + 输入管理 + 自定义右键菜单 + 引用回复。
// 所有 Pinia store 接口不动——chatStore/sessionStore 消费方式不变。
import { ref, nextTick, watch, onMounted } from 'vue'
import { useChatStore } from '@/stores/chat'
import { useSessionStore } from '@/stores/session'
import { useShellStore } from '@/stores/shell'
// WHY SSE composable 保留——Phase C 后续接线 SSE streaming 时使用
// import { useEventSource } from '@/composables/useEventSource'
import type { ChatMessage } from '@/stores/chat'
import MessageItem from '@/components/chat/MessageItem.vue'
import InputBox from '@/components/chat/InputBox.vue'
import QuoteChip from '@/components/chat/QuoteChip.vue'
import ContextMenu from '@/components/chat/ContextMenu.vue'

const chat = useChatStore()
const session = useSessionStore()
const shell = useShellStore()
// const sse = useEventSource()  // WHY Phase C 后续接线 SSE

// 消息列表容器 ref——自动滚动到底部
const messageListRef = ref<HTMLDivElement | null>(null)
const inputRef = ref<InstanceType<typeof InputBox> | null>(null)

// 右键菜单状态
const contextMenuVisible = ref(false)
const contextMenuPos = ref({ x: 0, y: 0 })
const contextMenuMessage = ref<ChatMessage | null>(null)

// 历史导航
const historyIndex = ref(-1)
const historyBuffer = ref<string[]>([])

// 虚拟滚动——消息 >200 条时启用（Phase C 先手写简单实现，后续换 @tanstack/vue-virtual）
const VISIBLE_RANGE = 100
const enableVirtualScroll = ref(false)

// WHY chatStore.messages 是响应式数组，直接渲染。
// 消息由 chatStore.send() 和 SSE stream 追加，此处只读。

function scrollToBottom() {
  nextTick(() => {
    if (messageListRef.value) {
      messageListRef.value.scrollTop = messageListRef.value.scrollHeight
    }
  })
}

// 监听新消息——自动滚动
watch(() => chat.messages.length, () => {
  scrollToBottom()
  if (chat.messages.length > 200) {
    enableVirtualScroll.value = true
  }
})

// 发送消息
function onSend(text: string) {
  if (!session.currentSessionId) return

  // 附加引用
  let fullText = text
  if (shell.quoteTarget) {
    fullText = `[引用 agent> ${shell.quoteTarget.text.slice(0, 60)}...]\n${text}`
    shell.setQuoteTarget(null)
  }

  chat.send(fullText, session.currentSessionId, session.currentProjectName || '')

  // 记录到历史
  historyBuffer.value.push(text)
  historyIndex.value = historyBuffer.value.length

  scrollToBottom()
}

// 历史导航
function onNavigateHistory(direction: -1 | 1) {
  if (historyBuffer.value.length === 0) return
  historyIndex.value += direction
  if (historyIndex.value < 0) historyIndex.value = 0
  if (historyIndex.value >= historyBuffer.value.length) historyIndex.value = historyBuffer.value.length
  // 设置到 InputBox 的 text——此处通过 expose 或 store
}

// 右键菜单
function openContextMenu(event: MouseEvent, msg: ChatMessage) {
  contextMenuPos.value = { x: event.clientX, y: event.clientY }
  contextMenuMessage.value = msg
  contextMenuVisible.value = true
}

function closeContextMenu() {
  contextMenuVisible.value = false
  contextMenuMessage.value = null
}

function onContextAction(action: string) {
  const msg = contextMenuMessage.value
  if (!msg) return

  switch (action) {
    case 'copy':
      navigator.clipboard.writeText(msg.text)
      break
    case 'copy-link':
      // WHY 复制消息链接：后续可实现消息锚点跳转
      navigator.clipboard.writeText(`#msg-${msg.id}`)
      break
    case 'quote':
      shell.setQuoteTarget(msg)
      inputRef.value?.focus()
      break
    case 'open-file':
      // 尝试从消息文本中提取文件路径
      const match = msg.text.match(/(?:^|\s)(\S+\.(?:py|ts|vue|js|tsx|jsx|css|html|md))/)
      if (match) {
        shell.openFileReview(match[1])
      }
      break
    case 'retry':
      if (session.currentSessionId) {
        chat.send(msg.text, session.currentSessionId, session.currentProjectName || '')
      }
      break
  }
  closeContextMenu()
}

// 获取可见消息（简单虚拟滚动）
function visibleMessages(): ChatMessage[] {
  if (!enableVirtualScroll.value) return chat.messages
  const start = Math.max(0, chat.messages.length - VISIBLE_RANGE)
  return chat.messages.slice(start)
}

onMounted(() => {
  scrollToBottom()
})
</script>

<template>
  <div class="terminal-chat flex flex-col h-full">
    <!-- 消息列表 -->
    <div
      ref="messageListRef"
      class="message-list flex-1 overflow-y-auto"
    >
      <!-- 虚拟滚动头部占位 -->
      <div
        v-if="enableVirtualScroll"
        :style="{ height: Math.max(0, chat.messages.length - VISIBLE_RANGE) * 28 + 'px' }"
      />

      <MessageItem
        v-for="msg in visibleMessages()"
        :key="msg.id"
        :message="msg"
        @contextmenu="(e: MouseEvent) => openContextMenu(e, msg)"
      />

      <!-- 连接中指示器 -->
      <div
        v-if="chat.connecting"
        class="px-4 py-1 text-xs flex items-center gap-2"
        style="color: var(--color-orbit-warn); font-family: var(--font-mono);"
      >
        <span class="status-dot connecting" />
        connecting...
      </div>

      <!-- 错误提示 -->
      <div
        v-if="chat.lastError"
        class="px-4 py-1 text-xs"
        style="color: var(--color-orbit-error); font-family: var(--font-mono);"
      >
        ✗ {{ chat.lastError }}
      </div>
    </div>

    <!-- 输入区域 -->
    <div
      class="input-area"
      style="border-top: 1px solid var(--color-orbit-border);"
    >
      <!-- 引用气泡 -->
      <QuoteChip
        v-if="shell.quoteTarget"
        :message="shell.quoteTarget"
        @dismiss="shell.setQuoteTarget(null)"
      />

      <!-- 输入框 -->
      <InputBox
        ref="inputRef"
        @send="onSend"
        @navigate-history="onNavigateHistory"
      />
    </div>

    <!-- 全局右键菜单 -->
    <ContextMenu
      v-if="contextMenuVisible && contextMenuMessage"
      :message="contextMenuMessage"
      :x="contextMenuPos.x"
      :y="contextMenuPos.y"
      @close="closeContextMenu"
      @copy="onContextAction('copy')"
      @copy-link="onContextAction('copy-link')"
      @quote="onContextAction('quote')"
      @open-file="onContextAction('open-file')"
      @retry="onContextAction('retry')"
    />
  </div>
</template>

<style scoped>
.terminal-chat {
  font-family: var(--font-mono);
}

.message-list {
  /* WHY overflow-y: auto ——消息超出容器高度时滚动，输入框保持固定在底部 */
  scroll-behavior: smooth;
}
</style>
