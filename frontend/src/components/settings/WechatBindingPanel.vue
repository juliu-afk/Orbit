<!-- 微信绑定面板——QR 码展示 + 状态指示 + 断开/刷新 + 推送配置。
     WHY 独立 Drawer 而非嵌在 ConfigDrawer 内：ConfigDrawer 已较复杂，
     微信绑定有独立的状态机（pending→active→disconnected），独立更清晰。 -->
<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue'
import { apiGet, apiPost, apiDelete } from '@/services/api'

const props = defineProps<{ show: boolean }>()
const emit = defineEmits<{ (e: 'update:show', v: boolean): void }>()

// ── 状态 ──
type BindStatus = 'unbound' | 'pending' | 'active' | 'disconnected'
const status = ref<BindStatus>('unbound')
const qrcodeUrl = ref('')
const expiresAt = ref('')
const wechatNickname = ref('')
const loading = ref(false)
const error = ref('')

// 倒计时
const countdown = ref(300)  // 5 分钟
let timer: ReturnType<typeof setInterval> | null = null

// ── 操作 ──

async function fetchStatus(): Promise<void> {
  try {
    const data = await apiGet<{ status: BindStatus; wechat_nickname: string | null; connected_at: string | null }>('/api/v1/wechat/bind/status')
    status.value = data.status
    wechatNickname.value = data.wechat_nickname ?? ''
  } catch {
    status.value = 'unbound'
  }
}

async function startBind(): Promise<void> {
  loading.value = true
  error.value = ''
  try {
    const data = await apiPost<{ bind_token: string; qrcode_data_url: string; expires_at: string }>('/api/v1/wechat/bind/start', {})
    qrcodeUrl.value = data.qrcode_data_url
    expiresAt.value = data.expires_at
    status.value = 'pending'
    countdown.value = 300
    startCountdown()
    startPolling()
  } catch (e) {
    error.value = e instanceof Error ? e.message : '生成二维码失败'
  } finally {
    loading.value = false
  }
}

async function unbind(): Promise<void> {
  try {
    await apiDelete('/api/v1/wechat/bind')
    status.value = 'unbound'
    qrcodeUrl.value = ''
    stopCountdown()
    stopPolling()
  } catch (e) {
    error.value = e instanceof Error ? e.message : '断开失败'
  }
}

// ── 轮询 + 倒计时 ──
let pollTimer: ReturnType<typeof setInterval> | null = null

function startPolling(): void {
  pollTimer = setInterval(async () => {
    await fetchStatus()
    if (status.value === 'active') {
      stopCountdown()
      stopPolling()
    }
  }, 3000)  // 每 3 秒查一次
}

function stopPolling(): void {
  if (pollTimer) { clearInterval(pollTimer); pollTimer = null }
}

function startCountdown(): void {
  timer = setInterval(() => {
    countdown.value--
    if (countdown.value <= 0) {
      stopCountdown()
      // 过期不自动关闭，用户需手动刷新
    }
  }, 1000)
}

function stopCountdown(): void {
  if (timer) { clearInterval(timer); timer = null }
}

function formatCountdown(s: number): string {
  const m = Math.floor(s / 60)
  const sec = s % 60
  return `${m}:${sec.toString().padStart(2, '0')}`
}

// ── 生命周期 ──
onMounted(() => { if (props.show) fetchStatus() })
onUnmounted(() => { stopCountdown(); stopPolling() })
</script>

<template>
  <el-drawer
    :model-value="props.show"
    title="微信连接"
    direction="rtl"
    size="420px"
    @update:model-value="emit('update:show', $event as boolean)"
  >
    <div class="wechat-panel">
      <!-- 状态指示 -->
      <div class="status-section">
        <div class="status-row">
          <span class="status-dot" :class="status" />
          <span class="status-text">
            {{ status === 'active' ? '已连接' : status === 'pending' ? '等待扫码…' : status === 'disconnected' ? '已断开' : '未绑定' }}
          </span>
        </div>
        <p v-if="wechatNickname" class="wechat-name">微信号: {{ wechatNickname }}</p>
      </div>

      <!-- QR 码——仅 pending 状态 -->
      <div v-if="status === 'pending' && qrcodeUrl" class="qr-section">
        <img :src="qrcodeUrl" alt="微信绑定二维码" class="qr-image" />
        <p class="qr-hint">用微信小号扫描二维码绑定</p>
        <p class="qr-countdown" :class="{ expired: countdown <= 0 }">
          {{ countdown > 0 ? `二维码 ${formatCountdown(countdown)} 后过期` : '二维码已过期' }}
        </p>
      </div>

      <!-- 操作按钮 -->
      <div class="actions">
        <button v-if="status === 'unbound' || status === 'disconnected'" class="btn primary" :disabled="loading" @click="startBind">
          {{ loading ? '生成中…' : '连接微信' }}
        </button>
        <button v-if="status === 'pending'" class="btn secondary" @click="startBind" :disabled="loading">
          刷新二维码
        </button>
        <button v-if="status === 'active'" class="btn danger" @click="unbind">
          断开连接
        </button>
      </div>

      <!-- 错误 -->
      <div v-if="error" class="error-msg">{{ error }}</div>

      <!-- 配置（P2） -->
      <div class="config-section">
        <h4>推送偏好</h4>
        <p class="config-note">每日摘要时间、静默时段等（待实现）</p>
      </div>

      <!-- 帮助 -->
      <div class="help-section">
        <h4>说明</h4>
        <ul>
          <li>需使用 <strong>微信小号</strong>，不建议绑定主号</li>
          <li>微信是驾驶舱伴随通道，不替代 Web 界面</li>
          <li>消息频率受限：最多 5 条/分钟</li>
          <li>断开后可在驾驶舱随时重新绑定</li>
        </ul>
      </div>
    </div>
  </el-drawer>
</template>

<style scoped>
.wechat-panel { padding: 8px 0; font-family: var(--font-mono); font-size: 13px; color: var(--color-orbit-text); }

.status-section { margin-bottom: 20px; }
.status-row { display: flex; align-items: center; gap: 8px; }
.status-dot { width: 10px; height: 10px; border-radius: 50%; background: #64748b; }
.status-dot.active { background: #22c55e; }
.status-dot.pending { background: #f59e0b; animation: pulse 1.5s infinite; }
.status-dot.disconnected { background: #ef4444; }
@keyframes pulse { 0%, 100% { opacity: 1; } 50% { opacity: 0.4; } }
.status-text { font-size: 15px; font-weight: 600; }
.wechat-name { font-size: 12px; color: var(--color-orbit-text-muted); margin: 4px 0 0 18px; }

.qr-section { text-align: center; margin: 20px 0; }
.qr-image { width: 200px; height: 200px; border-radius: 8px; border: 1px solid var(--color-orbit-border); }
.qr-hint { font-size: 12px; color: var(--color-orbit-text-muted); margin: 10px 0 4px; }
.qr-countdown { font-size: 12px; color: var(--color-orbit-accent); }
.qr-countdown.expired { color: #ef4444; }

.actions { margin: 16px 0; }
.btn { padding: 8px 20px; border: none; border-radius: 4px; cursor: pointer; font-family: inherit; font-size: 13px; }
.btn:disabled { opacity: 0.5; cursor: not-allowed; }
.btn.primary { background: var(--color-orbit-accent); color: #fff; }
.btn.secondary { background: rgba(255,255,255,.06); color: var(--color-orbit-text); border: 1px solid var(--color-orbit-border); }
.btn.danger { background: rgba(239,68,68,.15); color: #ef4444; border: 1px solid rgba(239,68,68,.3); }

.error-msg { padding: 8px 12px; background: rgba(239,68,68,.1); border-radius: 4px; color: #ef4444; font-size: 12px; margin: 8px 0; }

.config-section, .help-section { margin-top: 24px; padding-top: 16px; border-top: 1px solid var(--color-orbit-border); }
.config-section h4, .help-section h4 { font-size: 13px; margin: 0 0 8px; color: #e0e0e0; }
.config-note { font-size: 12px; color: var(--color-orbit-text-muted); }
.help-section ul { padding-left: 16px; font-size: 12px; color: var(--color-orbit-text-secondary); }
.help-section li { margin: 4px 0; }
</style>
