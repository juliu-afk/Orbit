<!-- BootScreen.vue: 启动预检全屏界面——终端风格重绘（Step 10）。去掉 el-progress/el-icon/el-button -->
<template>
  <div class="boot-screen glass flex justify-center" style="padding-top: 12vh;">
    <div style="width: 520px; max-width: 90vw;">
      <!-- 标题 -->
      <div class="text-center mb-6">
        <h1
          class="text-3xl font-bold m-0 tracking-wider"
          style="color: var(--color-orbit-accent); font-family: var(--font-mono);"
        >
          Orbit
        </h1>
        <p
          class="text-xs mt-1"
          style="color: var(--color-orbit-text-muted); font-family: var(--font-mono);"
        >
          Multi-Agent Development System
        </p>
      </div>

      <!-- 状态文字 -->
      <p
        class="text-center text-sm mb-4"
        style="font-family: var(--font-mono); color: var(--color-orbit-text-secondary);"
      >
        <template v-if="preflight.status === 'booting'">$ connecting to backend...</template>
        <template v-else-if="preflight.status === 'running'">$ running system checks...</template>
        <template v-else-if="preflight.status === 'passed'">✓ all checks passed</template>
        <template v-else>✗ checks failed</template>
      </p>

      <!-- 进度条——终端风格 [=====>    ] -->
      <div class="mb-6">
        <div
          class="progress-track"
          style="
            height: 6px;
            background: var(--color-orbit-border-light);
            border-radius: 3px;
            overflow: hidden;
          "
        >
          <div
            class="progress-fill"
            :style="{
              width: preflight.progress + '%',
              height: '100%',
              background: preflight.status === 'failed'
                ? 'var(--color-orbit-error)'
                : preflight.status === 'passed'
                  ? 'var(--color-orbit-accent)'
                  : 'var(--color-orbit-info)',
              transition: 'width 0.3s ease',
            }"
          />
        </div>
        <div
          class="text-right text-[10px] mt-1"
          style="color: var(--color-orbit-text-muted); font-family: var(--font-mono);"
        >
          {{ preflight.progress }}%
        </div>
      </div>

      <!-- 检查列表 -->
      <div class="mb-4" v-if="preflight.checks.length > 0" style="font-family: var(--font-mono);">
        <div
          v-for="c in preflight.checks"
          :key="c.name"
          class="check-item flex items-center gap-2 py-1.5 text-xs"
          :style="{ color: checkColor(c.status) }"
        >
          <!-- 状态图标——纯 Unicode，不用 el-icon -->
          <span class="check-icon w-5 text-center shrink-0">
            <template v-if="c.status === 'pending'">◌</template>
            <template v-else-if="c.status === 'running'">
              <span class="inline-block" style="animation: spin 1s linear infinite;">◌</span>
            </template>
            <template v-else-if="c.status === 'passed'">✓</template>
            <template v-else-if="c.status === 'failed'">✗</template>
            <template v-else-if="c.status === 'repaired'">🔧</template>
            <template v-else-if="c.status === 'skipped'">→</template>
          </span>
          <span class="shrink-0" style="width: 100px;">{{ c.label }}</span>
          <span class="flex-1 text-[11px] truncate" style="opacity: 0.7;">{{ c.message }}</span>
          <span
            v-if="c.duration_ms > 0"
            class="shrink-0 text-[10px]"
            style="color: var(--color-orbit-text-muted);"
          >
            {{ c.duration_ms }}ms
          </span>
        </div>
      </div>

      <!-- 自愈提示 -->
      <div
        v-if="preflight.repairedItems.length > 0"
        class="mb-3 p-2.5 rounded text-xs leading-relaxed"
        style="
          background: rgba(255,152,0,0.1);
          border-left: 3px solid var(--color-orbit-warn);
          color: var(--color-orbit-warn);
          font-family: var(--font-mono);
        "
      >
        ✓ auto-repaired {{ preflight.autoRepairs }}:
        <template v-for="(r, i) in preflight.repairedItems" :key="r.name">
          {{ r.label }}（{{ r.message }}）{{ i < preflight.repairedItems.length - 1 ? ', ' : '' }}
        </template>
      </div>

      <!-- 失败 + 重试 / 安装 -->
      <div v-if="preflight.hasFailed" class="text-center mt-3">
        <p
          class="text-xs mb-3"
          style="color: var(--color-orbit-error); font-family: var(--font-mono);"
        >
          {{ preflight.errorMessage }}
        </p>
        <div class="flex justify-center gap-2">
          <button
            class="terminal-btn"
            style="
              background: var(--color-orbit-accent-dim);
              border: 1px solid var(--color-orbit-accent);
              color: var(--color-orbit-text);
            "
            @click="preflight.retry()"
          >
            重新检测
          </button>
          <template v-for="c in preflight.checks" :key="'btn-' + c.name">
            <button
              v-if="c.status === 'failed' && c.install_action"
              class="terminal-btn"
              :disabled="installing[c.name]"
              style="
                background: rgba(255,152,0,0.15);
                border: 1px solid var(--color-orbit-warn);
                color: var(--color-orbit-warn);
              "
              @click="handleInstall(c.name, c.install_action)"
            >
              {{ installing[c.name] ? 'installing...' : `安装 ${c.label}` }}
            </button>
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

function checkColor(status: string): string {
  switch (status) {
    case 'running': return 'var(--color-orbit-info)'
    case 'passed': return 'var(--color-orbit-accent)'
    case 'failed': return 'var(--color-orbit-error)'
    case 'repaired': return 'var(--color-orbit-warn)'
    default: return 'var(--color-orbit-text-secondary)'
  }
}

async function handleInstall(name: string, action: string) {
  installing[name] = true
  preflight.stopPolling()
  const component = action.replace('install_', '')
  await preflight.installComponent(component)
  installing[name] = false
}

defineExpose({ preflight })
</script>

<style scoped>
.boot-screen {
  min-height: 100vh;
  background: var(--color-orbit-bg);
}

.terminal-btn {
  font-family: var(--font-mono);
  font-size: 12px;
  padding: 6px 16px;
  border-radius: 4px;
  cursor: pointer;
  transition: opacity 0.15s;
}
.terminal-btn:hover:not(:disabled) {
  opacity: 0.85;
}
.terminal-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

@keyframes spin {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}
</style>
