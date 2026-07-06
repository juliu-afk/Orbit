<script setup lang="ts">
import { ref, computed, nextTick, watch, onMounted } from 'vue'
import { useChatStore } from '@/stores/chat'
import { useSessionStore } from '@/stores/session'
import { useShellStore } from '@/stores/shell'
import { useEditorStore } from '@/stores/editor'
import type { ChatMessage } from '@/stores/chat'
import MessageItem from '@/components/chat/MessageItem.vue'
import InputBox from '@/components/chat/InputBox.vue'
import QuoteChip from '@/components/chat/QuoteChip.vue'
import ContextMenu from '@/components/chat/ContextMenu.vue'
import SkeletonPanel from '@/components/common/SkeletonPanel.vue'  // UX-6

const chat = useChatStore()
const session = useSessionStore()
const shell = useShellStore()
const editor = useEditorStore()

const messageListRef = ref<HTMLDivElement | null>(null)
const inputRef = ref<InstanceType<typeof InputBox> | null>(null)

const ctxVisible = ref(false)
const ctxPos = ref({ x: 0, y: 0 })
const ctxMsg = ref<ChatMessage | null>(null)

const historyBuf = ref<string[]>([])
const historyIdx = ref(-1)
const enableVS = ref(false)

// UX-3: 消息历史搜索
const searchQuery = ref('')
const searchVisible = ref(false)

const filteredMsgs = computed<ChatMessage[]>(() => {
  const msgs = visibleMsgs.value
  if (!searchQuery.value.trim()) return msgs
  const q = searchQuery.value.toLowerCase()
  return msgs.filter(m => m.text.toLowerCase().includes(q))
})

function scrollBottom() { nextTick(() => { if (messageListRef.value) messageListRef.value.scrollTop = messageListRef.value.scrollHeight }) }
watch(() => chat.messages.length, () => { scrollBottom(); if (chat.messages.length > 200) enableVS.value = true })

function onSend(text: string) {
  if (!session.currentSessionId) return
  let ft = text
  if (shell.quoteTarget) { ft = `[quote agent> ${shell.quoteTarget.text.slice(0, 60)}...]\n${text}`; shell.setQuoteTarget(null) }
  chat.send(ft, session.currentSessionId, session.currentProjectName || '')
  historyBuf.value.push(text); historyIdx.value = historyBuf.value.length
  scrollBottom()
}

// 从 historyBuf 恢复输入——ArrowUp 向旧消息、ArrowDown 向新消息
function onNavHistory(d: -1 | 1) {
  const next = historyIdx.value + d
  if (next < 0) return  // 已到最早
  if (next >= historyBuf.value.length) {  // 已到最新→清空
    historyIdx.value = historyBuf.value.length
    inputRef.value?.setText('')
    return
  }
  historyIdx.value = next
  inputRef.value?.setText(historyBuf.value[next] ?? '')
}

function openCtx(e: MouseEvent, msg: ChatMessage) { ctxPos.value = { x: e.clientX, y: e.clientY }; ctxMsg.value = msg; ctxVisible.value = true }
function closeCtx() { ctxVisible.value = false; ctxMsg.value = null }

function onCtxAct(action: string) {
  const msg = ctxMsg.value; if (!msg) return
  switch (action) {
    case 'copy': navigator.clipboard.writeText(msg.text); break
    case 'quote': shell.setQuoteTarget(msg); inputRef.value?.focus(); break
    case 'open-file': const m = msg.text.match(/(\S+\.(?:py|ts|vue|js|tsx|css|html|md))/); if (m) shell.openFileReview(m[1]); break
    case 'retry': if (session.currentSessionId) chat.send(msg.text, session.currentSessionId, session.currentProjectName || ''); break
  }
  closeCtx()
}

// WHY: 聊天代码块 ↗ 按钮 → 在右侧 Monaco 面板打开编辑
function onOpenCode(code: string) {
  editor.openCode(code, 'python')
  shell.openFileReview('[code]')
}

// P2-5 fix: computed 缓存切片结果，避免每次渲染重新 slice
const visibleMsgs = computed<ChatMessage[]>(() => { if (!enableVS.value) return chat.messages; const s = Math.max(0, chat.messages.length - 100); return chat.messages.slice(s) })

onMounted(() => scrollBottom())
</script>

<template>
<div class="terminal-chat flex flex-col h-full" style="font-family:var(--font-mono)">
  <!-- UX-3: 消息搜索栏 -->
  <div v-if="searchVisible" class="search-bar">
    <input v-model="searchQuery" class="search-input" placeholder="Search messages..." @keydown.escape="searchQuery='';searchVisible=false" />
    <span class="search-count" v-if="searchQuery">{{ filteredMsgs.length }}/{{ chat.messages.length }}</span>
    <button class="search-close" @click="searchQuery='';searchVisible=false">✕</button>
  </div>
  <div ref="messageListRef" class="message-list flex-1 overflow-y-auto" style="scroll-behavior:smooth">
    <div v-if="enableVS" :style="{ height: Math.max(0, chat.messages.length - 100) * 28 + 'px' }" />
    <!-- UX-6: 首次加载时骨架屏 -->
    <SkeletonPanel v-if="chat.connecting && chat.messages.length === 0" :lines="6" height="auto" />
    <MessageItem v-for="msg in filteredMsgs" :key="msg.id" :message="msg" @contextmenu="(e:MouseEvent) => openCtx(e, msg)" @open-code="onOpenCode" />
    <div v-if="chat.connecting && chat.messages.length > 0" class="px-4 py-1 text-xs flex items-center gap-2" style="color:var(--color-orbit-warn)"><span class="status-dot connecting"/>connecting...</div>
    <div v-if="chat.lastError" class="px-4 py-1 text-xs" style="color:var(--color-orbit-error)">x {{ chat.lastError }}</div>
  </div>
  <div class="input-area" style="border-top:1px solid var(--color-orbit-border)">
    <!-- UX-3: 搜索触发按钮 -->
    <div v-if="!searchVisible && chat.messages.length > 0" class="px-3 pt-1 flex justify-end">
      <button class="search-trigger" @click="searchVisible=true;searchQuery=''">🔍</button>
    </div>
    <QuoteChip v-if="shell.quoteTarget" :message="shell.quoteTarget" @dismiss="shell.setQuoteTarget(null)" />
    <InputBox ref="inputRef" @send="onSend" @navigate-history="onNavHistory" />
  </div>
  <ContextMenu v-if="ctxVisible && ctxMsg" :message="ctxMsg" :x="ctxPos.x" :y="ctxPos.y" @close="closeCtx" @copy="onCtxAct('copy')" @quote="onCtxAct('quote')" @open-file="onCtxAct('open-file')" @retry="onCtxAct('retry')" />
</div>
</template>

<!-- UX-3: 搜索栏样式 -->
<style scoped>
.search-bar { display:flex;align-items:center;gap:6px;padding:6px 12px;border-bottom:1px solid var(--color-orbit-border);background:var(--color-orbit-glass) }
.search-input { flex:1;background:transparent;border:none;outline:none;color:var(--color-orbit-text);font-size:12px;font-family:var(--font-mono) }
.search-count { font-size:10px;color:var(--color-orbit-text-secondary);white-space:nowrap }
.search-close { padding:0 6px;border:none;background:transparent;color:var(--color-orbit-text-secondary);cursor:pointer;font-size:12px }
.search-trigger { padding:2px 6px;border:none;background:transparent;cursor:pointer;font-size:12px;opacity:.5 }
.search-trigger:hover { opacity:1 }
</style>
