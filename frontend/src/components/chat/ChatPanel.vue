<!-- ???????????? + Agent ?? + ???? + PRD ???? -->
<template>
  <div class="chat-panel">
    <!-- ?????????????? -->
    <div v-if="chatStore.candidates.length > 0" class="chat-panel__candidates">
      <div class="chat-panel__candidates-title">
        ???? ({{ chatStore.candidates.length }})
      </div>
      <CandidateCard
        v-for="(c, i) in chatStore.candidates.slice(0, 5)"
        :key="c.project"
        :candidate="c"
        :is-top="i === 0 && chatStore.candidates.length > 1"
        @confirm="handleConfirmProject"
      />
    </div>

    <!-- ?????user / agent / system? -->
    <div ref="msgListRef" class="chat-panel__messages">
      <div v-if="chatStore.messages.length === 0" class="chat-panel__empty">
        ???????????Agent ???????
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

    <!-- ???????Agent ??????? -->
    <div
      v-if="showAcceptanceOptions"
      class="chat-panel__acceptance"
    >
      <div class="acceptance-title">????????????</div>
      <label
        v-for="opt in chatStore.structuredPrd?.acceptance_options"
        :key="opt"
        class="acceptance-option"
      >
        <input type="checkbox" :value="opt" v-model="selectedAcceptance" />
        <span>{{ opt }}</span>
      </label>
      <!-- ?????????????? -->
      <label class="acceptance-option">
        <input type="checkbox" v-model="useCustomAcceptance" />
        <span>??</span>
      </label>
      <input
        v-if="useCustomAcceptance"
        v-model="customAcceptance"
        class="acceptance-input"
        placeholder="?????????..."
      />
      <el-button type="primary" size="small" @click="submitAcceptance">??</el-button>
    </div>

    <!-- PRD ?????clarification_status=ready ???? -->
    <div v-if="showPrdConfirm" class="chat-panel__prd">
      <div class="prd-title">?????????????</div>
      <div class="prd-field">
        <label>??</label>
        <textarea v-model="editablePrd.goal" rows="2" class="prd-input"></textarea>
      </div>
      <div class="prd-field">
        <label>??</label>
        <textarea v-model="editablePrd.scope" rows="2" class="prd-input"></textarea>
      </div>
      <div class="prd-field">
        <label>????</label>
        <div
          v-for="(_ac, i) in editablePrd.acceptance_criteria"
          :key="i"
          class="prd-ac-item"
        >
          <input v-model="editablePrd.acceptance_criteria[i]" class="prd-input" />
        </div>
      </div>
      <div class="prd-actions">
        <el-button type="primary" @click="handleConfirmPrd">???????</el-button>
      </div>
    </div>

    <!-- ??????? -->
    <div v-if="chatStore.lastTaskId" class="chat-panel__task">
      ??????{{ chatStore.lastTaskId }}???????
    </div>

    <!-- ???? -->
    <div v-if="chatStore.lastError" class="chat-panel__error">
      {{ chatStore.lastError }}
    </div>

    <!-- ??? -->
    <div class="chat-panel__input">
      <el-input
        v-model="inputText"
        placeholder="??????..."
        :disabled="chatStore.connecting"
        @keyup.enter="handleSend"
        clearable
      >
        <template #append>
          <el-button
            :disabled="!inputText.trim() || chatStore.connecting"
            @click="handleSend"
          >
            ??
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

const chatStore = useChatStore()
const sessionStore = useSessionStore()
const inputText = ref('')
const msgListRef = ref<HTMLElement | null>(null)

// ????????
const selectedAcceptance = ref<string[]>([])
const useCustomAcceptance = ref(false)
const customAcceptance = ref('')

// PRD ????????????
const editablePrd = reactive<StructuredPRD>({
  goal: '',
  scope: '',
  acceptance_criteria: [],
})

// ???????? acceptance_options ????
const showAcceptanceOptions = computed(() => {
  const opts = chatStore.structuredPrd?.acceptance_options
  return Array.isArray(opts) && opts.length > 0 && chatStore.clarificationStatus === 'clarifying'
})

// ?? PRD ???ready ?? structured_prd
const showPrdConfirm = computed(() => {
  return chatStore.clarificationStatus === 'ready' && chatStore.structuredPrd !== null
})

// ready ??????? PRD
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

function handleConfirmProject(project: string) {
  chatStore.confirm(project)
}

function submitAcceptance() {
  // ??????? + ?????
  const merged = [...selectedAcceptance.value]
  if (useCustomAcceptance.value && customAcceptance.value.trim()) {
    merged.push(customAcceptance.value.trim())
  }
  if (merged.length > 0 && chatStore.structuredPrd) {
    // ?? acceptance_criteria ???
    chatStore.structuredPrd.acceptance_criteria = merged
    chatStore.structuredPrd.acceptance_options = []
    // ??????? Agent
    chatStore.send(
      `????????${merged.join('?')}`,
      sessionStore.currentSessionId || '',
      sessionStore.currentProjectName,
    )
  }
  selectedAcceptance.value = []
  useCustomAcceptance.value = false
  customAcceptance.value = ''
}

function handleConfirmPrd() {
  // ???????????? PRD?
  chatStore.confirmPrd(
    sessionStore.currentSessionId || '',
    sessionStore.currentProjectName,
    { ...editablePrd },
  )
}

// ???????????
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

.chat-panel__acceptance {
  padding: 10px; margin-bottom: 12px;
  background: #0a2a1a; border: 1px solid #4caf50; border-radius: 8px;
}
.acceptance-title { font-size: 13px; color: #c0e0c0; margin-bottom: 8px; }
.acceptance-option {
  display: flex; align-items: center; gap: 6px;
  padding: 4px 0; font-size: 13px; color: #c0e0c0; cursor: pointer;
}
.acceptance-input {
  width: 100%; margin: 4px 0 8px;
  padding: 6px 8px; background: #0a1a0a; color: #e0e0e0;
  border: 1px solid #4caf50; border-radius: 4px;
}
.chat-panel__prd {
  padding: 12px; margin-bottom: 12px;
  background: #1a1a3a; border: 1px solid #646cff; border-radius: 8px;
}
.prd-title { font-size: 14px; color: #c0c0e0; margin-bottom: 10px; font-weight: 600; }
.prd-field { margin-bottom: 10px; }
.prd-field label { display: block; font-size: 12px; color: #8888aa; margin-bottom: 4px; }
.prd-input {
  width: 100%; padding: 6px 8px; background: #0a0a14; color: #e0e0e0;
  border: 1px solid #2a2a4a; border-radius: 4px; font-size: 13px;
}
.prd-ac-item { margin-bottom: 4px; }
.prd-actions { margin-top: 10px; }
.chat-panel__task {
  padding: 8px 12px; margin-bottom: 8px;
  background: #0a2a0a; border: 1px solid #4caf50; border-radius: 8px;
  color: #c0e0c0; font-size: 13px;
}
.chat-panel__error {
  padding: 8px 12px; margin-bottom: 8px;
  background: #2a0a0a; border: 1px solid #f44336; border-radius: 8px;
  color: #e0c0c0; font-size: 13px;
}
.chat-panel__input { padding-top: 8px; border-top: 1px solid #2a2a4a; }
</style>
