<!-- BootScreen.vue: 启动预检全屏界面——进度条+逐项检查+自愈提示 -->
<template>
  <div class="boot-screen">
    <div class="boot-card">
      <!-- 标题 -->
      <div class="boot-header">
        <h1 class="boot-title">Orbit</h1>
        <p class="boot-subtitle">Multi-Agent Development System</p>
      </div>

      <!-- 状态文字 -->
      <p class="boot-status">
        <template v-if="preflight.status === 'booting'">正在连接后端...</template>
        <template v-else-if="preflight.status === 'running'">正在检查系统组件...</template>
        <template v-else-if="preflight.status === 'passed'">✅ 所有检查通过</template>
        <template v-else>⚠️ 检查未通过</template>
      </p>

      <!-- 进度条 -->
      <el-progress
        :percentage="preflight.progress"
        :status="preflight.status === 'failed' ? 'exception' : preflight.status === 'passed' ? 'success' : undefined"
        :stroke-width="8"
        :show-text="false"
        class="boot-progress"
      />

      <!-- 检查列表 -->
      <div class="check-list" v-if="preflight.checks.length > 0">
        <div
          v-for="c in preflight.checks"
          :key="c.name"
          class="check-item"
          :class="`check-item--${c.status}`"
        >
          <span class="check-icon">
            <template v-if="c.status === 'pending'">◌</template>
            <template v-else-if="c.status === 'running'">
              <el-icon class="is-loading"><Loading /></el-icon>
            </template>
            <template v-else-if="c.status === 'passed'">✓</template>
            <template v-else-if="c.status === 'failed'">✗</template>
            <template v-else-if="c.status === 'repaired'">🔧</template>
            <template v-else-if="c.status === 'skipped'">→</template>
          </span>
          <span class="check-label">{{ c.label }}</span>
          <span class="check-msg">{{ c.message }}</span>
          <span v-if="c.duration_ms > 0" class="check-time">{{ c.duration_ms }}ms</span>
        </div>
      </div>

      <!-- 自愈提示 -->
      <div v-if="preflight.repairedItems.length > 0" class="repaired-notice">
        已自动修复 {{ preflight.autoRepairs }} 项：
        <template v-for="(r, i) in preflight.repairedItems" :key="r.name">
          {{ r.label }}（{{ r.message }}）{{ i < preflight.repairedItems.length - 1 ? '、' : '' }}
        </template>
      </div>

      <!-- 失败 + 重试 -->
      <div v-if="preflight.hasFailed" class="failed-section">
        <p class="failed-msg">{{ preflight.errorMessage }}</p>
        <div class="failed-actions">
          <el-button type="primary" @click="preflight.retry()">
            重新检测
          </el-button>
          <template v-for="c in preflight.checks" :key="'btn-' + c.name">
            <el-button
              v-if="c.status === 'failed' && c.install_action"
              type="warning"
              :loading="installing[c.name]"
              @click="handleInstall(c.name, c.install_action)"
            >
              安装 {{ c.label }}
            </el-button>
          </template>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { reactive } from 'vue'
import { usePreFlightStore } from '@/stores/preflight'

const preflight = usePreFlightStore()
const installing = reactive<Record<string, boolean>>({})

async function handleInstall(name: string, _action: string) {
  installing[name] = true
  preflight.stopPolling()
  await preflight.installComponent(name)
  installing[name] = false
}

defineExpose({ preflight })
</script>

<style scoped>
.boot-screen {
  min-height: 100vh;
  background: #0a0a14;
  display: flex;
  justify-content: center;
  align-items: flex-start;
  padding-top: 12vh;
}
.boot-card {
  width: 520px;
  max-width: 90vw;
}
.boot-header {
  text-align: center;
  margin-bottom: 24px;
}
.boot-title {
  font-size: 32px;
  font-weight: 700;
  color: #4caf50;
  margin: 0;
  letter-spacing: 2px;
}
.boot-subtitle {
  font-size: 13px;
  color: #666;
  margin: 4px 0 0;
}
.boot-status {
  text-align: center;
  font-size: 14px;
  color: #888;
  margin-bottom: 16px;
}
.boot-progress {
  margin-bottom: 24px;
}
.boot-progress :deep(.el-progress-bar__outer) {
  background: #1a1a2e;
}

.check-list {
  margin-bottom: 16px;
}
.check-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 0;
  font-size: 13px;
  color: #888;
}
.check-item--running { color: #409eff; }
.check-item--passed { color: #4caf50; }
.check-item--failed { color: #f44336; }
.check-item--repaired { color: #ff9800; }
.check-icon {
  width: 20px;
  text-align: center;
  flex-shrink: 0;
  font-size: 14px;
}
.check-label {
  width: 100px;
  flex-shrink: 0;
}
.check-msg {
  flex: 1;
  font-size: 12px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.check-time {
  font-size: 11px;
  color: #555;
  flex-shrink: 0;
}

.repaired-notice {
  padding: 10px 14px;
  background: rgba(255, 152, 0, 0.1);
  border-left: 3px solid #ff9800;
  border-radius: 4px;
  font-size: 12px;
  color: #ff9800;
  margin-bottom: 12px;
  line-height: 1.6;
}

.failed-section {
  text-align: center;
  margin-top: 12px;
}
.failed-msg {
  font-size: 13px;
  color: #f44336;
  margin-bottom: 12px;
}
.failed-actions {
  display: flex;
  justify-content: center;
  gap: 8px;
}
</style>
