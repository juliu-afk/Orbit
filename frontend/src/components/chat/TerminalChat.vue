<script setup lang="ts">
import { ref, nextTick, watch, onMounted } from 'vue'
import { useChatStore } from '@/stores/chat'
import { useSessionStore } from '@/stores/session'
import { useShellStore } from '@/stores/shell'
import type { ChatMessage } from '@/stores/chat'
import MessageItem from '@/components/chat/MessageItem.vue'
import InputBox from '@/components/chat/InputBox.vue'
import QuoteChip from '@/components/chat/QuoteChip.vue'
import ContextMenu from '@/components/chat/ContextMenu.vue'

const chat = useChatStore()
const session = useSessionStore()
const shell = useShellStore()

const messageListRef = ref<HTMLDivElement | null>(null)
const inputRef = ref<InstanceType<typeof InputBox> | null>(null)

const ctxVisible = ref(false)
const ctxPos = ref({ x: 0, y: 0 })
const ctxMsg = ref<ChatMessage | null>(null)

const historyBuf = ref<string[]>([])
const historyIdx = ref(-1)
const enableVS = ref(false)

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

function onNavHistory(d: -1 | 1) { /* TODO */ }

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

function visibleMsgs(): ChatMessage[] { if (!enableVS.value) return chat.messages; const s = Math.max(0, chat.messages.length - 100); return chat.messages.slice(s) }

onMounted(() => scrollBottom())
</script>

<template>
<div class="terminal-chat flex flex-col h-full" style="font-family:var(--font-mono)">
  <div ref="messageListRef" class="message-list flex-1 overflow-y-auto" style="scroll-behavior:smooth">
    <div v-if="enableVS" :style="{ height: Math.max(0, chat.messages.length - 100) * 28 + 'px' }" />
    <MessageItem v-for="msg in visibleMsgs()" :key="msg.id" :message="msg" @contextmenu="(e:MouseEvent) => openCtx(e, msg)" />
    <div v-if="chat.connecting" class="px-4 py-1 text-xs flex items-center gap-2" style="color:var(--color-orbit-warn)"><span class="status-dot connecting"/>connecting...</div>
    <div v-if="chat.lastError" class="px-4 py-1 text-xs" style="color:var(--color-orbit-error)">x {{ chat.lastError }}</div>
  </div>
  <div class="input-area" style="border-top:1px solid var(--color-orbit-border)">
    <QuoteChip v-if="shell.quoteTarget" :message="shell.quoteTarget" @dismiss="shell.setQuoteTarget(null)" />
    <InputBox ref="inputRef" @send="onSend" @navigate-history="onNavHistory" />
  </div>
  <ContextMenu v-if="ctxVisible && ctxMsg" :message="ctxMsg" :x="ctxPos.x" :y="ctxPos.y" @close="closeCtx" @copy="onCtxAct('copy')" @quote="onCtxAct('quote')" @open-file="onCtxAct('open-file')" @retry="onCtxAct('retry')" />
</div>
</template>
