<!-- 自然语言聊天面板：输入框 + 候选列表 + 消息历史 -->
<template>
  <div class="chat-panel">
    <!-- 候选项目卡片 -->
    <div v-if="chatStore.candidates.length > 0" class="chat-panel__candidates">
      <div class="chat-panel__candidates-title">
        匹配结果 ({{ chatStore.candidates.length }})
      </div>
      <CandidateCard
        v-for="(c, i) in chatStore.candidates.slice(0, 5)"
        :key="c.project"
        :candidate="c"
        :is-top="i === 0 && chatStore.candidates.length > 1"
        @confirm="handleConfirm"
      />
    </div>

    <!-- 消息历史 -->
    <div ref="msgListRef" class="chat-panel__messages">
      <div v-if="chatStore.messages.length === 0" class="chat-panel__empty">
        输入自然语言描述，自动匹配项目
      </div>
      <div
        v-for="m in chatStore.messages"
        :key="m.id"
        class="chat-msg"
        :class="`chat-msg--${m.from}`"
      >
        <span class="chat-msg__text">{{ m.text }}</span>
      </div>
    </div>

    <!-- O2 批量确认卡片 -->
    <div v-if="showBatchConfirm" class="chat-panel__batch">
      <span class="batch-text">{{ batchConfirmText }}</span>
      <el-button type="primary" size="small" @click="handleBatchConfirm">开始</el-button>
    </div>

    <!-- 输入框 -->
    <div class="chat-panel__input">
      <el-input
        v-model="inputText"
        placeholder="描述你的需求..."
        :disabled="chatStore.connecting"
        @keyup.enter="handleSend"
        clearable
      >
        <template #append>
          <el-button
            :disabled="!inputText.trim() || chatStore.connecting"
            @click="handleSend"
          >
            发送
          </el-button>
        </template>
      </el-input>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, ref, watch } from 'vue'
import { useChatStore } from '@/stores/chat'
import { useSessionStore } from '@/stores/session'
import CandidateCard from './CandidateCard.vue'

const chatStore = useChatStore()
const sessionStore = useSessionStore()
const inputText = ref('')
const batchConfirmed = ref(false)

// O2: 批量确认——候选人=1 且 >0.8 分时自动展示"开始"按钮
const showBatchConfirm = computed(() => {
  if (batchConfirmed.value) return false
  const c = chatStore.candidates
  return c.length === 1 && c[0].score >= 0.8 && !chatStore.requiresConfirmation
})

const batchConfirmText = computed(() => {
  const c = chatStore.candidates[0]
  return `准备就绪——项目: ${c?.project}, 匹配度: ${Math.round((c?.score ?? 0) * 100)}%`
})

function handleBatchConfirm() {
  if (chatStore.candidates[0]) {
    chatStore.confirm(chatStore.candidates[0].project)
    batchConfirmed.value = true
  }
}
const msgListRef = ref<HTMLElement | null>(null)

function handleSend() {
  if (!inputText.value.trim()) return
  // Session PR #3: 附 session_id + project_name
  chatStore.send(
    inputText.value,
    sessionStore.currentSessionId || '',
    sessionStore.currentProjectName,
  )
  inputText.value = ''
}

function handleConfirm(project: string) {
  chatStore.confirm(project)
}

// 新消息到达时滚动到底部
watch(() => chatStore.messages.length, () => {
  nextTick(() => {
    if (msgListRef.value) {
      msgListRef.value.scrollTop = msgListRef.value.scrollHeight
    }
  })
})
</script>

<style scoped>
.chat-panel {
  display: flex; flex-direction: column; height: 100%;
  min-height: 500px; padding: 12px;
}
.chat-panel__candidates {
  margin-bottom: 12px;
}
.chat-panel__candidates-title {
  font-size: 13px; color: #8888aa; margin-bottom: 8px;
}
.chat-panel__messages {
  flex: 1; overflow-y: auto; margin-bottom: 12px;
  padding: 8px; background: #0a0a14; border-radius: 8px;
  min-height: 200px;
}
.chat-panel__empty {
  text-align: center; padding: 40px 20px;
  color: #6666aa; font-size: 14px;
}
.chat-msg { margin-bottom: 8px; padding: 8px 12px; border-radius: 8px; max-width: 85%; }
.chat-msg--user { background: #1a3a5c; margin-left: auto; text-align: right; color: #e0e0e0; }
.chat-msg--system { background: #16163a; margin-right: auto; color: #8888aa; font-size: 13px; }
.chat-msg__text { word-break: break-word; }
.chat-panel__batch {
  display: flex; align-items: center; justify-content: space-between;
  padding: 10px 14px; margin-top: 8px;
  background: #0a3a0a; border: 1px solid #4caf50; border-radius: 8px;
}
.batch-text { font-size: 13px; color: #c0e0c0; flex: 1; margin-right: 12px; }
.chat-panel__input { padding-top: 8px; border-top: 1px solid #2a2a4a; }
</style>
