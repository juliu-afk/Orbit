<!-- ChatSessionTabs.vue: 聊天顶部会话标签栏——右键关闭/分屏，标题限8字符 -->
<template>
  <div class="session-tabs-bar" @click.self="showCtx = false">
    <!-- 左：过往会话历史 -->
    <el-dropdown
      v-if="session.sessions.length > 0"
      @command="handleHistorySwitch"
      trigger="click"
    >
      <button class="tabs-btn tabs-btn--history" title="过往会话">
        🕐
      </button>
      <template #dropdown>
        <el-dropdown-menu>
          <el-dropdown-item
            v-for="s in session.sessions"
            :key="s.session_id"
            :command="s.session_id"
            :class="{ 'is-active': s.session_id === session.currentSessionId }"
          >
            <span class="history-item-title">{{ shortTitle(s) }}</span>
            <span class="history-item-path">{{ s.local_path || s.project_name }}</span>
          </el-dropdown-item>
        </el-dropdown-menu>
      </template>
    </el-dropdown>

    <!-- 中：会话标签——仅显示有标题的会话（有内容才值得留） -->
    <div class="tabs-scroll" v-if="session.currentSessionId">
      <button
        v-for="s in titledSessions"
        :key="s.session_id"
        class="tabs-tab"
        :class="{ 'tabs-tab--active': s.session_id === session.currentSessionId }"
        @click="handleTabClick(s.session_id)"
        @contextmenu.prevent="openCtx($event, s)"
        :title="s.project_name"
      >
        {{ shortTitle(s) }}
      </button>
    </div>
    <span v-else class="tabs-placeholder" />

    <!-- 右：新建会话 -->
    <button class="tabs-btn tabs-btn--new" @click="showPicker = true" title="新建会话">+</button>

    <ProjectPickerDialog
      v-model:visible="showPicker"
      @pick="onCreateSession"
    />

    <!-- 右键菜单 -->
    <div
      v-if="showCtx"
      class="tabs-ctx-menu"
      :style="{ left: ctxX + 'px', top: ctxY + 'px' }"
      @click.stop
    >
      <button class="tabs-ctx-item" @click="handleCloseSession">✕ 关闭</button>
      <button class="tabs-ctx-item" @click="handleSplitSession">↗ 分屏</button>
    </div>

    <!-- WHY 点击空白区关闭菜单 -->
    <div v-if="showCtx" class="tabs-ctx-backdrop" @click="showCtx = false" />
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useSessionStore, type SessionSummary } from '@/stores/session'
import ProjectPickerDialog from '@/components/layout/ProjectPickerDialog.vue'

const emit = defineEmits<{
  'switch-session': [sessionId: string]
  'split-session': [sessionId: string]
}>()

const session = useSessionStore()
const showPicker = ref(false)

// WHY: 仅显示有标题的会话——无标题=空会话，不占标签位
const titledSessions = computed(() =>
  session.sessions.filter(s => s.title || s.session_id === session.currentSessionId)
)

// ── 右键菜单状态 ──
const showCtx = ref(false)
const ctxX = ref(0)
const ctxY = ref(0)
const ctxSession = ref<SessionSummary | null>(null)

// WHY: 标题——仅显示摘要，最多 8 个字符；无标题的会话只显示 +
function shortTitle(s: { title: string; project_name: string }): string {
  if (s.title) {
    const parts = s.title.split('_')
    const summary = parts.length > 1 ? parts.slice(1).join('_') : s.title
    return summary.length > 8 ? summary.slice(0, 8) + '…' : summary
  }
  return '+'
}

// WHY: 首条用户消息到达时自动持久化标题——仅在 title 为空时生成一次
watch(
  () => session.messages.length,
  async () => {
    if (!session.currentSessionId) return
    if (session.currentTitle) return
    const firstUser = session.messages.find(m => m.role === 'user')
    if (!firstUser) return
    const text = firstUser.content.replace(/\n/g, ' ').trim()
    const short = text.length > 20 ? text.slice(0, 20) + '...' : text
    const title = `${session.currentProjectName}_${short}`
    await session.updateTitle(session.currentSessionId, title)
  },
)

function handleTabClick(sessionId: string) {
  showCtx.value = false
  if (sessionId === session.currentSessionId) return
  session.switchToSession(sessionId)
  emit('switch-session', sessionId)
}

function handleHistorySwitch(sessionId: string) {
  if (sessionId === session.currentSessionId) return
  session.switchToSession(sessionId)
  emit('switch-session', sessionId)
}

async function onCreateSession(projectName: string) {
  try {
    await session.createSession(projectName)
    emit('switch-session', session.currentSessionId!)
  } catch { /* 静默 */ }
}

// ── 右键菜单 ──
function openCtx(e: MouseEvent, s: SessionSummary) {
  showCtx.value = false  // 先关旧的
  // WHY: 相对父容器定位——避免超出视口
  const bar = (e.currentTarget as HTMLElement).closest('.session-tabs-bar')
  const barRect = bar?.getBoundingClientRect() ?? { left: 0, top: 0 }
  ctxX.value = e.clientX - barRect.left
  ctxY.value = 28  // 固定在标签栏下方
  ctxSession.value = s
  // 异步显示避免被同一 click 关掉
  setTimeout(() => { showCtx.value = true }, 0)
}

async function handleCloseSession() {
  showCtx.value = false
  if (!ctxSession.value) return
  await session.archiveSession(ctxSession.value.session_id)
  emit('switch-session', session.currentSessionId!)
}

function handleSplitSession() {
  showCtx.value = false
  if (!ctxSession.value) return
  emit('split-session', ctxSession.value.session_id)
}

</script>

<style scoped>
.session-tabs-bar {
  display: flex; align-items: center;
  height: 32px; position: relative;
  background: rgba(10,10,20,0.92);
  border-bottom: 1px solid var(--color-orbit-border);
  font-family: var(--font-mono);
  font-size: 12px;
  flex-shrink: 0;
}

/* ── 按钮通用 ── */
.tabs-btn {
  display: flex; align-items: center; justify-content: center;
  width: 32px; height: 32px;
  background: none; border: none;
  color: var(--color-orbit-text-secondary);
  font-family: var(--font-mono); font-size: 14px;
  cursor: pointer;
  flex-shrink: 0;
  transition: background 0.15s, color 0.15s;
}
.tabs-btn:hover { background: rgba(255,255,255,0.06); color: var(--color-orbit-text); }
.tabs-btn--new {
  font-size: 18px; font-weight: 300;
  color: var(--color-orbit-accent);
}
.tabs-btn--new:hover { background: rgba(76,175,80,0.12); }

/* ── 标签滚动区 ── */
.tabs-scroll {
  flex: 1; display: flex; align-items: center;
  overflow-x: auto; overflow-y: hidden;
  gap: 1px; padding: 0 4px;
  scrollbar-width: none;
}
.tabs-scroll::-webkit-scrollbar { display: none; }

/* ── 单个标签 ── */
.tabs-tab {
  display: flex; align-items: center;
  height: 26px; padding: 0 8px;
  background: transparent; border: none; border-radius: 4px;
  color: var(--color-orbit-text-secondary);
  font-family: var(--font-mono); font-size: 11px;
  cursor: pointer;
  white-space: nowrap;
  transition: background 0.15s, color 0.15s;
  max-width: 100px;
  overflow: hidden; text-overflow: ellipsis;
}
.tabs-tab:hover { background: rgba(255,255,255,0.06); color: var(--color-orbit-text); }
.tabs-tab--active {
  background: rgba(76,175,80,0.12); color: var(--color-orbit-accent);
  font-weight: 500;
}

.tabs-placeholder {
  flex: 1; padding: 0 12px;
  color: var(--color-orbit-text-muted); font-size: 11px;
}

/* ── 历史下拉项 ── */
.history-item-title { font-size: 12px; font-weight: 500; color: #e0e0e0; }
.history-item-path { display: block; font-size: 10px; color: #666; margin-top: 1px; }
.is-active .history-item-title { color: var(--color-orbit-accent); }

/* ── 右键菜单 ── */
.tabs-ctx-menu {
  position: absolute;
  z-index: 100;
  background: #1a1a2e;
  border: 1px solid #2a2a4a;
  border-radius: 6px;
  padding: 4px 0;
  min-width: 80px;
  box-shadow: 0 4px 12px rgba(0,0,0,0.4);
}
.tabs-ctx-item {
  display: block; width: 100%; padding: 6px 14px;
  background: none; border: none;
  color: #c0c0c0; font-family: var(--font-mono); font-size: 12px;
  cursor: pointer; text-align: left;
  transition: background 0.1s;
}
.tabs-ctx-item:hover { background: rgba(76,175,80,0.12); color: #fff; }
.tabs-ctx-backdrop {
  position: fixed; inset: 0; z-index: 99;
  /* 透明遮罩——点击关闭右键菜单 */
}
</style>
