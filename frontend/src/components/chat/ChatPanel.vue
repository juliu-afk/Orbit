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

    <!-- Agent验收选项 -->
    <div v-if="showAcceptanceOptions" class="chat-panel__acceptance">
      <div class="acceptance-title">选择验收标准</div>
      <label
        v-for="opt in chatStore.structuredPrd?.acceptance_options"
        :key="opt"
        class="acceptance-option"
      >
        <input type="checkbox" :value="opt" v-model="selectedAcceptance" />
        <span>{{ opt }}</span>
      </label>
      <!-- 自定义验收标准 -->
      <label class="acceptance-option">
        <input type="checkbox" v-model="useCustomAcceptance" />
        <span>自定义</span>
      </label>
      <input
        v-if="useCustomAcceptance"
        v-model="customAcceptance"
        class="acceptance-input"
        placeholder="请输入自定义验收标准..."
      />
      <el-button type="primary" size="small" @click="submitAcceptance">提交</el-button>
    </div>

    <!-- PRD确认（clarification_status=ready时显示） -->
    <div v-if="showPrdConfirm" class="chat-panel__prd">
      <div class="prd-title">请确认需求文档</div>
      <div class="prd-field">
        <label>目标</label>
        <textarea v-model="editablePrd.goal" rows="2" class="prd-input"></textarea>
      </div>
      <div class="prd-field">
        <label>范围</label>
        <textarea v-model="editablePrd.scope" rows="2" class="prd-input"></textarea>
      </div>
      <div class="prd-field">
        <label>验收标准</label>
        <div
          v-for="(_ac, i) in editablePrd.acceptance_criteria"
          :key="i"
          class="prd-ac-item"
        >
          <input v-model="editablePrd.acceptance_criteria[i]" class="prd-input" />
        </div>
      </div>
      <div class="prd-actions">
        <el-button type="primary" @click="handleConfirmPrd">确认并提交任务</el-button>
      </div>
    </div>

    <!-- 任务状态 -->
    <div v-if="chatStore.lastTaskId" class="chat-panel__task">
      任务已创建：{{ chatStore.lastTaskId }}
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

// Agent 角色 → 展示名 + emoji + 颜色 映射
const AGENT_META: Record<string, { label: string; emoji: string; color: string }> = {
  clarifier:    { label: 'Clarifier',  emoji: '💬', color: '#4caf50' },
  architect:    { label: 'Architect',  emoji: '📐', color: '#2196f3' },
  developer:    { label: 'Developer',  emoji: '💻', color: '#ff9800' },
  reviewer:     { label: 'Reviewer',   emoji: '🔎', color: '#9c27b0' },
  qa:           { label: 'QA',         emoji: '✅', color: '#00bcd4' },
  config_manager:{ label: 'Config',    emoji: '⚙️', color: '#607d8b' },
}
function agentLabel(role: string): string { return AGENT_META[role]?.label ?? role }
function agentEmoji(role: string): string { return AGENT_META[role]?.emoji ?? '🤖' }
function agentColor(role: string): string { return AGENT_META[role]?.color ?? '#666' }

const chatStore = useChatStore()
const sessionStore = useSessionStore()
const inputText = ref('')
const msgListRef = ref<HTMLElement | null>(null)

// 验收选项状态
const selectedAcceptance = ref<string[]>([])
const useCustomAcceptance = ref(false)
const customAcceptance = ref('')

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

function submitAcceptance() {
  // 合并已选+自定义验收标准
  const merged = [...selectedAcceptance.value]
  if (useCustomAcceptance.value && customAcceptance.value.trim()) {
    merged.push(customAcceptance.value.trim())
  }
  if (merged.length > 0 && chatStore.structuredPrd) {
    chatStore.structuredPrd.acceptance_criteria = merged
    chatStore.structuredPrd.acceptance_options = []
    // 发送验收选择给Agent
    chatStore.send(
      `验收标准：${merged.join('；')}`,
      sessionStore.currentSessionId || '',
      sessionStore.currentProjectName,
    )
  }
  selectedAcceptance.value = []
  useCustomAcceptance.value = false
  customAcceptance.value = ''
}

function handleConfirmPrd() {
  // 确认PRD并提交任务
  chatStore.confirmPrd(
    sessionStore.currentSessionId || '',
    sessionStore.currentProjectName,
    { ...editablePrd },
  )
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
