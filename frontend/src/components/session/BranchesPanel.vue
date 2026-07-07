<!-- 对话分支面板——UX 长期 #13 -->
<script setup lang="ts">
import { onMounted } from 'vue'
import { useSessionStore, type SessionSummary } from '@/stores/session'

const session = useSessionStore()

onMounted(() => {
  session.fetchChildSessions()
})

function switchToChild(child: SessionSummary) {
  session.switchToSession(child.session_id)
}

function forkLatest() {
  session.forkSession()
}
</script>

<template>
  <div class="branches-panel">
    <div class="bp-header">
      <span class="bp-title">Branches</span>
      <button class="bp-fork-btn" @click="forkLatest" title="Fork current session">
        + Fork
      </button>
    </div>
    <div v-if="session.childSessions.length === 0" class="bp-empty">
      No branches yet
    </div>
    <div v-else class="bp-list">
      <div
        v-for="child in session.childSessions"
        :key="child.session_id"
        class="bp-item"
        :class="{ active: child.session_id === session.currentSessionId }"
        @click="switchToChild(child)"
      >
        <span class="bp-item-title">{{ child.title || child.session_id.slice(0, 8) }}</span>
        <span class="bp-item-time">{{ new Date(child.created_at * 1000).toLocaleString() }}</span>
      </div>
    </div>
  </div>
</template>

<style scoped>
.branches-panel {
  padding: 8px 12px;
  font-family: var(--font-mono);
  font-size: 11px;
  color: var(--color-orbit-text-secondary);
}
.bp-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
}
.bp-title {
  font-size: 10px;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  color: var(--color-orbit-accent);
}
.bp-fork-btn {
  padding: 2px 8px;
  font-size: 10px;
  font-family: var(--font-mono);
  background: var(--color-orbit-accent-dim);
  border: 1px solid var(--color-orbit-accent);
  border-radius: 4px;
  color: var(--color-orbit-accent);
  cursor: pointer;
}
.bp-fork-btn:hover { opacity: 0.8; }
.bp-empty {
  font-size: 10px;
  color: var(--color-orbit-text-muted);
  padding: 8px 0;
}
.bp-list {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.bp-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 4px 8px;
  border-radius: 4px;
  cursor: pointer;
  transition: background 0.15s;
}
.bp-item:hover { background: var(--color-orbit-surface); }
.bp-item.active { background: var(--color-orbit-accent-dim); }
.bp-item-title { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; max-width: 160px; }
.bp-item-time { font-size: 9px; color: var(--color-orbit-text-muted); white-space: nowrap; }
</style>
