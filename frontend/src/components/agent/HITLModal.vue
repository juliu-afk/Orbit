<!--
  HITL (Human-in-the-Loop) 人工干预弹窗
  Phase A: Agent 五大能力——元认知层 Monitor 检测到 CRITICAL → 暂停主 Agent → 弹窗

  用户响应选项:
    · 继续执行 (CONTINUE)  ——确认无风险，继续
    · 回滚 (ROLLBACK)       ——回退到上一检查点
    · 退回反思 (STEP_BACK)   ——退回一步，重新反思对准目标
    · 终止任务 (ABORT)      ——放弃当前任务

  props:
    visible: boolean ——是否显示弹窗
    request: HITLRequest ——Monitor 发来的请求上下文
    loading: boolean ——等待中状态
-->
<template>
  <Teleport to="body">
    <Transition name="hitl-fade">
      <div v-if="visible" class="hitl-overlay" @click.self="/* 不响应——强制用户做选择 */">
        <div class="hitl-modal" role="alertdialog" aria-labelledby="hitl-title">
          <!-- 头部 -->
          <div class="hitl-header" :class="severityClass">
            <span class="hitl-icon">{{ severityIcon }}</span>
            <h2 id="hitl-title">{{ severityLabel }}：需要人工决策</h2>
          </div>

          <!-- 正文 -->
          <div class="hitl-body">
            <p class="hitl-message">{{ request?.message || 'Agent 检测到异常，需要人工介入' }}</p>

            <div v-if="request?.original_goal" class="hitl-context">
              <h4>原始目标</h4>
              <p>{{ request.original_goal }}</p>
            </div>

            <div v-if="request?.context?.recent_actions?.length" class="hitl-context">
              <h4>最近动作</h4>
              <ul class="hitl-actions">
                <li v-for="(a, i) in request.context.recent_actions" :key="i">
                  <code>{{ a }}</code>
                </li>
              </ul>
            </div>

            <div v-if="request?.alert_type" class="hitl-meta">
              <span class="hitl-tag">{{ request.alert_type }}</span>
              <span v-if="request?.current_state" class="hitl-state">当前状态: {{ request.current_state }}</span>
            </div>
          </div>

          <!-- 操作按钮 -->
          <div class="hitl-footer">
            <button
              class="hitl-btn hitl-btn-continue"
              :disabled="loading"
              @click="$emit('respond', 'continue')"
            >
              继续执行
            </button>
            <button
              class="hitl-btn hitl-btn-stepback"
              :disabled="loading"
              @click="$emit('respond', 'step_back')"
            >
              退回反思
            </button>
            <button
              class="hitl-btn hitl-btn-rollback"
              :disabled="loading"
              @click="$emit('respond', 'rollback')"
            >
              回滚
            </button>
            <button
              class="hitl-btn hitl-btn-abort"
              :disabled="loading"
              @click="$emit('respond', 'abort')"
            >
              终止任务
            </button>
          </div>

          <div v-if="loading" class="hitl-loading">处理中...</div>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<script setup lang="ts">
import { computed } from 'vue'

interface HITLRequest {
  alert_type: string
  severity: string
  message: string
  original_goal?: string
  current_state?: string
  suggested_action?: string
  context?: {
    recent_actions?: string[]
    drift_count?: number
    alert_count?: Record<string, number>
  }
}

defineProps<{
  visible: boolean
  request: HITLRequest | null
  loading: boolean
}>()

defineEmits<{
  respond: [action: 'continue' | 'rollback' | 'step_back' | 'abort']
}>()

const severityClass = computed(() => {
  return 'hitl-critical'  // Phase A: 目前只有 CRITICAL 触发弹窗
})

const severityIcon = computed(() => '⚠️')

const severityLabel = computed(() => '严重告警')
</script>

<style scoped>
.hitl-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.6);
  backdrop-filter: blur(4px);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 9999;
}
.hitl-modal {
  background: #1a1a2e;
  border: 1px solid #e53e3e;
  border-radius: 12px;
  max-width: 560px;
  width: 90vw;
  max-height: 80vh;
  overflow-y: auto;
  box-shadow: 0 0 40px rgba(229, 62, 62, 0.3);
}
.hitl-header {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 20px 24px;
  border-bottom: 1px solid #2d3748;
}
.hitl-critical .hitl-header {
  background: rgba(229, 62, 62, 0.1);
}
.hitl-icon {
  font-size: 1.5em;
}
.hitl-header h2 {
  margin: 0;
  font-size: 1.15em;
  color: #fc8181;
  font-weight: 600;
}
.hitl-body {
  padding: 20px 24px;
}
.hitl-message {
  font-size: 1.05em;
  color: #e2e8f0;
  margin: 0 0 16px 0;
  line-height: 1.6;
}
.hitl-context {
  margin-bottom: 12px;
}
.hitl-context h4 {
  margin: 0 0 6px 0;
  font-size: 0.8em;
  color: #a0aec0;
  text-transform: uppercase;
  letter-spacing: 0.5px;
}
.hitl-context p {
  margin: 0;
  color: #cbd5e0;
  font-size: 0.95em;
}
.hitl-actions {
  list-style: none;
  padding: 0;
  margin: 0;
}
.hitl-actions li {
  padding: 2px 0;
}
.hitl-actions code {
  font-size: 0.82em;
  color: #68d391;
  background: #1a202c;
  padding: 2px 6px;
  border-radius: 4px;
}
.hitl-meta {
  display: flex;
  gap: 10px;
  margin-top: 12px;
  align-items: center;
}
.hitl-tag {
  font-size: 0.75em;
  background: #e53e3e;
  color: #fff;
  padding: 2px 10px;
  border-radius: 10px;
  font-weight: 600;
}
.hitl-state {
  font-size: 0.82em;
  color: #718096;
}
.hitl-footer {
  display: flex;
  gap: 10px;
  padding: 16px 24px;
  border-top: 1px solid #2d3748;
  flex-wrap: wrap;
}
.hitl-btn {
  flex: 1;
  min-width: 100px;
  padding: 10px 16px;
  border: 1px solid;
  border-radius: 8px;
  font-size: 0.9em;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.15s;
  background: transparent;
  color: #e2e8f0;
}
.hitl-btn:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}
.hitl-btn-continue { border-color: #38a169; }
.hitl-btn-continue:hover:not(:disabled) { background: rgba(56, 161, 105, 0.15); }
.hitl-btn-stepback { border-color: #d69e2e; }
.hitl-btn-stepback:hover:not(:disabled) { background: rgba(214, 158, 46, 0.15); }
.hitl-btn-rollback { border-color: #dd6b20; }
.hitl-btn-rollback:hover:not(:disabled) { background: rgba(221, 107, 32, 0.15); }
.hitl-btn-abort { border-color: #e53e3e; }
.hitl-btn-abort:hover:not(:disabled) { background: rgba(229, 62, 62, 0.15); }
.hitl-loading {
  text-align: center;
  padding: 12px;
  color: #718096;
  font-size: 0.9em;
}

/* 过渡动画 */
.hitl-fade-enter-active, .hitl-fade-leave-active {
  transition: opacity 0.2s ease;
}
.hitl-fade-enter-from, .hitl-fade-leave-to {
  opacity: 0;
}
</style>
