<!-- SessionBar.vue: 顶栏——项目名 + Session 下拉 + 新建按钮 -->
<template>
  <div class="session-bar">
    <div class="session-bar__left">
      <span v-if="session.currentProjectName" class="project-badge">
        📁 {{ session.currentProjectName }}
      </span>
      <span v-else class="project-badge project-badge--empty">
        未选择项目
      </span>

      <el-dropdown
        v-if="session.sessions.length > 0"
        @command="handleSwitch"
        trigger="click"
      >
        <span class="session-dropdown-trigger">
          {{ session.currentTitle || '选择会话' }}
          <el-icon><ArrowDown /></el-icon>
        </span>
        <template #dropdown>
          <el-dropdown-menu>
            <el-dropdown-item
              v-for="s in session.sessions"
              :key="s.session_id"
              :command="s.session_id"
              :class="{ 'is-active': s.session_id === session.currentSessionId }"
            >
              <span class="dd-title">{{ s.title || '未命名会话' }}</span>
              <span class="dd-project">{{ s.project_name }}</span>
              <span v-if="s.local_path" class="dd-path">{{ s.local_path }}</span>
            </el-dropdown-item>
          </el-dropdown-menu>
        </template>
      </el-dropdown>
    </div>

    <div class="session-bar__right">
      <el-button size="small" type="primary" @click="$emit('new-session')">
        + 新建会话
      </el-button>
      <!-- 窗口控制按钮——无原生标题栏时的替代 -->
      <button class="win-btn" title="最小化" @click="winMinimize">─</button>
      <button class="win-btn" title="关闭" @click="winClose">✕</button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { useSessionStore } from '@/stores/session'
import { getCurrentWindow } from '@tauri-apps/api/window'

const session = useSessionStore()
const appWindow = getCurrentWindow()

defineEmits<{
  'new-session': []
  'switch-session': [sessionId: string]
}>()

function handleSwitch(sessionId: string) {
  session.switchToSession(sessionId)
}

function winMinimize() {
  appWindow.minimize()
}

function winClose() {
  appWindow.close()
}
</script>

<style scoped>
.session-bar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 8px 12px;
  background: #12122a;
  border-bottom: 1px solid #2a2a4a;
}
.session-bar__left {
  display: flex;
  align-items: center;
  gap: 12px;
}
.project-badge {
  font-size: 15px;
  font-weight: 600;
  color: #4caf50;
  padding: 4px 10px;
  background: rgba(76, 175, 80, 0.1);
  border-radius: 4px;
}
.project-badge--empty {
  color: #888;
  background: rgba(128, 128, 128, 0.1);
}
.session-dropdown-trigger {
  color: #c0c0c0;
  cursor: pointer;
  font-size: 13px;
  display: flex;
  align-items: center;
  gap: 4px;
}
.session-dropdown-trigger:hover {
  color: #fff;
}
.dd-title {
  font-weight: 500;
}
.dd-project {
  margin-left: 8px;
  font-size: 11px;
  color: #888;
}
.dd-path {
  display: block;
  margin-top: 1px;
  font-size: 10px;
  color: #666;
}
.is-active .dd-title {
  color: #4caf50;
}

.win-btn {
  width: 32px; height: 24px;
  border: none; background: transparent;
  color: #888; font-size: 14px; cursor: pointer;
  border-radius: 2px;
  margin-left: 4px;
}
.win-btn:hover { background: rgba(255,255,255,0.08); color: #e0e0e0; }
.win-btn:last-child:hover { background: #f44336; color: #fff; }
</style>
