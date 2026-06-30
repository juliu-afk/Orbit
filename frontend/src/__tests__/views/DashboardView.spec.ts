import { describe, it, expect, vi, beforeEach } from 'vitest'
import { shallowMount } from '@vue/test-utils'
import { ref } from 'vue'

// ── Mock useWebSocket composable ──────────────────────────────────────
const mockConnectionStatus = ref<string>('connected')
const mockRetryCount = ref(0)
const mockMaxRetries = 5
const mockConnect = vi.fn()
const mockDisconnect = vi.fn()
const mockSetMessageHandler = vi.fn()

vi.mock('@/composables/useWebSocket', () => ({
  useWebSocket: vi.fn(() => ({
    connectionStatus: mockConnectionStatus,
    retryCount: mockRetryCount,
    maxRetries: mockMaxRetries,
    connect: mockConnect,
    disconnect: mockDisconnect,
    setMessageHandler: mockSetMessageHandler,
  })),
}))

// ── Mock Pinia stores ─────────────────────────────────────────────────
const mockCurrentSessionId = ref<string | null>(null)
const mockSessionMessages = ref<any[]>([])
const mockSessions = ref<any[]>([])
const mockCurrentProjectName = ref('')
const mockFetchSessions = vi.fn()
const mockSwitchToSession = vi.fn()

vi.mock('@/stores/session', () => ({
  useSessionStore: vi.fn(() => ({
    currentSessionId: mockCurrentSessionId,
    currentProjectName: mockCurrentProjectName,
    messages: mockSessionMessages,
    sessions: mockSessions,
    fetchSessions: mockFetchSessions,
    switchToSession: mockSwitchToSession,
    loading: ref(false),
  })),
}))

const mockMetrics = ref<any>(null)
const mockAlerts = ref<any[]>([])
const mockOverallHealth = ref('unknown')
const mockHealth = ref<any[]>([])
const mockAgentOpsFetchAll = vi.fn()
const mockAgentOpsStartPolling = vi.fn()
const mockAgentOpsReset = vi.fn()
const mockHandleWsEvent = vi.fn()

vi.mock('@/stores/agentops', () => ({
  useAgentOpsStore: vi.fn(() => ({
    metrics: mockMetrics,
    alerts: mockAlerts,
    overallHealth: mockOverallHealth,
    health: mockHealth,
    fetchAll: mockAgentOpsFetchAll,
    startPolling: mockAgentOpsStartPolling,
    reset: mockAgentOpsReset,
    handleWsEvent: mockHandleWsEvent,
    loading: ref(false),
  })),
}))

const mockChatMessages = ref<any[]>([])
const mockCrossProjectWarning = ref<string | null>(null)
const mockChatConnectWs = vi.fn()
const mockChatDisconnect = vi.fn()

vi.mock('@/stores/chat', () => ({
  useChatStore: vi.fn(() => ({
    messages: mockChatMessages,
    crossProjectWarning: mockCrossProjectWarning,
    connectChatWs: mockChatConnectWs,
    disconnect: mockChatDisconnect,
    restoreMessages: vi.fn(),
    reset: vi.fn(),
  })),
}))

vi.mock('@/stores/task', () => ({
  useTaskStore: vi.fn(() => ({
    taskState: ref('IDLE'),
    progress: ref(0),
    hasCodeOutput: ref(false),
    codeOutput: ref(null),
    handleTaskUpdate: vi.fn(),
    consumeCodeOutput: vi.fn(),
  })),
}))

vi.mock('vue-router', () => ({
  useRoute: vi.fn(() => ({ params: {} })),
}))

// ── End mocks ─────────────────────────────────────────────────────────

import DashboardView from '@/views/DashboardView.vue'

// Element Plus stubs + local child component stubs
const stubs = {
  'el-empty': { template: '<div class="el-empty-stub"><slot /></div>' },
  'el-button': { template: '<button class="el-button-stub" @click="$emit(\'click\')"><slot /></button>' },
  'el-divider': { template: '<hr class="el-divider-stub" />' },
  'el-drawer': { template: '<div class="el-drawer-stub" v-if="modelValue"><slot /></div>', props: ['modelValue'] },
  'el-select': { template: '<select class="el-select-stub"><slot /></select>' },
  'el-option': { template: '<option class="el-option-stub" />' },
  // child components are auto-stubbed by shallowMount, but explicit stubs
  // can help with clarity
}

describe('DashboardView', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockCurrentSessionId.value = null
    mockConnectionStatus.value = 'connected'
    mockRetryCount.value = 0
    mockMetrics.value = null
    mockAlerts.value = []
    mockOverallHealth.value = 'unknown'
  })

  // ── Connection status ─────────────────────────────────────────

  it('renders connection status dot', () => {
    const wrapper = shallowMount(DashboardView, { global: { stubs } })
    expect(wrapper.find('.connection-dot').exists()).toBe(true)
    expect(wrapper.find('.dot--connected').exists()).toBe(true)
  })

  it('shows "已连接" label when connected', () => {
    const wrapper = shallowMount(DashboardView, { global: { stubs } })
    expect(wrapper.text()).toContain('已连接')
  })

  it('shows "连接中..." label when connecting', () => {
    mockConnectionStatus.value = 'connecting'
    const wrapper = shallowMount(DashboardView, { global: { stubs } })
    expect(wrapper.text()).toContain('连接中')
  })

  it('shows "已断开" label when disconnected', () => {
    mockConnectionStatus.value = 'disconnected'
    const wrapper = shallowMount(DashboardView, { global: { stubs } })
    expect(wrapper.text()).toContain('已断开')
  })

  // ── Session state ─────────────────────────────────────────────

  it('shows welcome panel when no session', () => {
    mockCurrentSessionId.value = null
    const wrapper = shallowMount(DashboardView, { global: { stubs } })
    expect(wrapper.find('.welcome').exists()).toBe(true)
    expect(wrapper.find('.workspace').exists()).toBe(false)
  })

  it('shows workspace when session exists', () => {
    mockCurrentSessionId.value = 'session-1'
    const wrapper = shallowMount(DashboardView, { global: { stubs } })
    expect(wrapper.find('.workspace').exists()).toBe(true)
    expect(wrapper.find('.welcome').exists()).toBe(false)
  })

  it('renders SessionBar component', () => {
    const wrapper = shallowMount(DashboardView, { global: { stubs } })
    // SessionBar is a local component — shallowMount stubs it automatically
    expect(wrapper.findComponent({ name: 'SessionBar' }).exists()).toBe(true)
  })

  it('renders ChatPanel component when session exists', () => {
    mockCurrentSessionId.value = 'session-1'
    const wrapper = shallowMount(DashboardView, { global: { stubs } })
    expect(wrapper.findComponent({ name: 'ChatPanel' }).exists()).toBe(true)
  })

  // ── Metrics sidebar (shown only when session exists) ──────────

  it('renders aside metrics section when session exists', () => {
    mockCurrentSessionId.value = 'session-1'
    mockMetrics.value = {
      active_tasks: 2,
      llm_tokens_total: { input: 100, output: 50 },
      hallucination_intercepted_total: { l3: 3 },
      circuit_breaker_state: { resource_guard: 0, z3: 0, sandbox: 0 },
    }
    mockOverallHealth.value = 'healthy'
    const wrapper = shallowMount(DashboardView, { global: { stubs } })
    expect(wrapper.find('.aside-section').exists()).toBe(true)
    expect(wrapper.text()).toContain('活跃任务')
    expect(wrapper.text()).toContain('正常')
  })
})
