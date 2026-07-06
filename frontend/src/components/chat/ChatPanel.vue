<!-- 自然语言聊天面板：输入框 + 候选列表 + Agent验收 + PRD确认 -->
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

    <!-- 消息历史（user / agent / system） -->
    <div ref="msgListRef" class="chat-panel__messages">
      <div v-if="chatStore.messages.length === 0" class="chat-panel__empty">
        输入自然语言描述，Agent自动分析需求
      </div>
      <div
        v-for="m in chatStore.messages"
        :key="m.id"
        class="chat-msg"
        :class="`chat-msg--${m.from}`"
      >
        <template v-if="m.from === 'agent' && m.role">
          <div class="chat-msg__agent-head">
            <span class="chat-msg__avatar" :style="{background: agentColor(m.role)}">
              {{ agentEmoji(m.role) }}
            </span>
            <span class="chat-msg__name">{{ agentLabel(m.role) }}</span>
          </div>
        </template>
        <span class="chat-msg__text">{{ m.text }}</span>
      </div>
    </div>

    <!-- Agent验收选项 + PRD确认——拆分到 PrdConfirmCard -->
    <PrdConfirmCard
      :show-acceptance-options="showAcceptanceOptions"
      :show-prd-confirm="showPrdConfirm"
      :acceptance-options="chatStore.structuredPrd?.acceptance_options ?? []"
      :editable-prd="editablePrd"
      @submit-acceptance="submitAcceptance"
      @confirm-prd="handleConfirmPrd"
    />

    <!-- Agent 流式执行——PRD 确认后串联 ChatStream -->
    <div v-if="chatStore.lastTaskId" class="chat-panel__execution">
      <div class="execution-header">
        <span class="execution-badge">执行中</span>
        <span class="execution-task-id">任务: {{ chatStore.lastTaskId }}</span>
      </div>
      <ChatStream
        :agent-id="'developer'"
        :task-id="chatStore.lastTaskId"
        class="chat-panel__stream"
        @finish="onStreamFinish"
        @error="onStreamError"
      />
    </div>

    <!-- 错误提示 -->
    <div v-if="chatStore.lastError" class="chat-panel__error">
      {{ chatStore.lastError }}
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
import { computed, nextTick, reactive, ref, watch } from 'vue'
import { useChatStore, type StructuredPRD } from '@/stores/chat'
import { useSessionStore } from '@/stores/session'
import CandidateCard from './CandidateCard.vue'
import ChatStream from './ChatStream.vue'
import PrdConfirmCard from './PrdConfirmCard.vue'

// Agent 角色 → 展示名 + emoji + 颜色 映射
const AGENT_META: Record<string, { label: string; emoji: string; color: string }> = {
  clarifier:    { label: 'Clarifier',  emoji: '💬', color: '#4caf50' },
  architect:    { label: 'Architect',  emoji: '📐', color: '#2196f3' },
  developer:    { label: 'Developer',  emoji: '💻', color: '#ff9800' },
  reviewer:     { label: 'Reviewer',   emoji: '🔎', color: '#9c27b0' },
  qa:           { label: 'QA',         emoji: '✅', color: '#00bcd4' },
  config_manager:{ label: 'Config',    emoji: '⚙️', color: '#607d8b' },
}
function agentLabel(role: string): string { return AGENT_META[role.toLowerCase()]?.label ?? role }
function agentEmoji(role: string): string { return AGENT_META[role.toLowerCase()]?.emoji ?? '🤖' }
function agentColor(role: string): string { return AGENT_META[role.toLowerCase()]?.color ?? '#666' }

const chatStore = useChatStore()
const sessionStore = useSessionStore()
const inputText = ref('')
const msgListRef = ref<HTMLElement | null>(null)

// PRD可编辑副本
const editablePrd = reactive<StructuredPRD>({
  goal: '',
  scope: '',
  acceptance_criteria: [],
})

// 是否显示验收选项（acceptance_options非空时）
const showAcceptanceOptions = computed(() => {
  const opts = chatStore.structuredPrd?.acceptance_options
  return Array.isArray(opts) && opts.length > 0 && chatStore.clarificationStatus === 'clarifying'
})

// 是否显示PRD确认（clarification_status=ready时）
const showPrdConfirm = computed(() => {
  return chatStore.clarificationStatus === 'ready' && chatStore.structuredPrd !== null
})

// ready时自动填充PRD到可编辑副本
watch(showPrdConfirm, (show) => {
  if (show && chatStore.structuredPrd) {
    editablePrd.goal = chatStore.structuredPrd.goal
    editablePrd.scope = chatStore.structuredPrd.scope
    editablePrd.acceptance_criteria = [...chatStore.structuredPrd.acceptance_criteria]
  }
})

function handleSend() {
  if (!inputText.value.trim()) return
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

function submitAcceptance(criteria: string[]) {
  if (criteria.length > 0 && chatStore.structuredPrd) {
    chatStore.structuredPrd.acceptance_criteria = criteria
    chatStore.structuredPrd.acceptance_options = []
    chatStore.send(
      `验收标准：${criteria.join('；')}`,
      sessionStore.currentSessionId || '',
      sessionStore.currentProjectName,
    )
  }
}

function handleConfirmPrd() {
  // 确认PRD并提交任务
  chatStore.confirmPrd(
    sessionStore.currentSessionId || '',
    sessionStore.currentProjectName,
    { ...editablePrd },
  )
}

// ChatStream 事件处理
function onStreamFinish(result: Record<string, unknown>) {
  // Agent 执行完成——可在驾驶舱展示完成通知
  if (import.meta.env.DEV) console.debug('ChatStream finished', result)
}

function onStreamError(message: string) {
  chatStore.lastError = `执行错误: ${message}`
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
  padding: 12px;
}
.chat-panel__candidates { margin-bottom: 12px; }
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
.chat-msg--agent { background: #1a2a3a; margin-right: auto; color: #b0c4de; }
.chat-msg--system { background: #16163a; margin-right: auto; color: #8888aa; font-size: 13px; }
.chat-msg__text { word-break: break-word; }
.chat-msg__agent-head {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-bottom: 4px;
}
.chat-msg__avatar {
  width: 20px;
  height: 20px;
  border-radius: 50%;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  font-size: 12px;
  flex-shrink: 0;
}
.chat-msg__name {
  font-size: 11px;
  font-weight: 600;
  color: #c0c0c0;
  letter-spacing: 0.5px;
}

.chat-panel__acceptance {
  padding: 10px; margin-bottom: 12px;
  background: #0a2a1a; border: 1px solid #4caf50; border-radius: 8px;
}
.acceptance-title { font-size: 13px; color: #c0e0c0; margin-bottom: 8px; font-weight: 500; }
.acceptance-option {
  display: flex; align-items: center; gap: 6px;
  padding: 4px 0; font-size: 13px; color: #c0c0c0; cursor: pointer;
}
.acceptance-input {
  width: 100%; margin-top: 6px; padding: 6px 10px;
  background: #0f1f0f; border: 1px solid #2a5a2a; border-radius: 4px;
  color: #c0c0c0; font-size: 13px;
}

.chat-panel__prd {
  padding: 12px; margin-bottom: 12px;
  background: #0a0a1a; border: 1px solid #2a2a5a; border-radius: 8px;
}
.prd-title { font-size: 14px; color: #e0e0e0; margin-bottom: 10px; font-weight: 500; }
.prd-field { margin-bottom: 8px; }
.prd-field label { font-size: 12px; color: #888; display: block; margin-bottom: 4px; }
.prd-input {
  width: 100%; padding: 6px 10px;
  background: #0f0f1a; border: 1px solid #2a2a4a; border-radius: 4px;
  color: #c0c0c0; font-size: 13px; resize: vertical;
}
.prd-ac-item { margin-bottom: 4px; }
.prd-actions { margin-top: 10px; }

.chat-panel__task {
  padding: 6px 10px; margin-bottom: 8px;
  background: #0a2a0a; border: 1px solid #4caf50; border-radius: 4px;
  font-size: 12px; color: #c0e0c0;
}

/* ── ChatStream 串联 ── */
.chat-panel__execution {
  margin-bottom: 12px;
  border: 1px solid #2a4a2a;
  border-radius: 8px;
  overflow: hidden;
}
.execution-header {
  display: flex; align-items: center; gap: 8px;
  padding: 6px 10px;
  background: #0a1a0a; border-bottom: 1px solid #2a4a2a;
}
.execution-badge {
  padding: 2px 8px; border-radius: 4px;
  background: #4caf50; color: #000;
  font-size: 11px; font-weight: 600;
  animation: pulse-badge 2s infinite;
}
@keyframes pulse-badge {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.6; }
}
.execution-task-id {
  font-size: 11px; color: #888;
  font-family: monospace;
}
.chat-panel__stream {
  max-height: 300px;
}
.chat-panel__error {
  padding: 6px 10px; margin-bottom: 8px;
  background: #2a0a0a; border: 1px solid #f44336; border-radius: 4px;
  font-size: 12px; color: #f44336;
}

.chat-panel__input { padding-top: 8px; border-top: 1px solid #2a2a4a; }

/* 覆盖 Element Plus 默认浅色边框 → 暗色主题 */
.chat-panel__input :deep(.el-input__wrapper) {
  background: #0f0f1a;
  border: 1px solid #2a2a4a;
  border-right: none;
  box-shadow: none;
}
.chat-panel__input :deep(.el-input__wrapper:hover) {
  border-color: #3a3a5a;
}
.chat-panel__input :deep(.el-input__wrapper.is-focus) {
  border-color: #4caf50;
}
.chat-panel__input :deep(.el-input__inner) {
  color: #c0c0c0;
}
.chat-panel__input :deep(.el-input-group__append) {
  background: #1a1a2e;
  border: 1px solid #2a2a4a;
  border-left: none;
}
/* 发送按钮——覆盖 Element Plus 默认亮色样式 */
.chat-panel__input :deep(.el-input-group__append .el-button) {
  background: transparent;
  border: none;
  color: #4caf50;
  font-size: 13px;
  padding: 0 12px;
  height: 100%;
  margin: 0;
}
.chat-panel__input :deep(.el-input-group__append .el-button:hover) {
  background: rgba(76, 175, 80, 0.08);
  color: #66bb6a;
}
.chat-panel__input :deep(.el-input-group__append .el-button:disabled) {
  color: #555;
  background: transparent;
}
</style>
