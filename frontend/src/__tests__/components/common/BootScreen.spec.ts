import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { ref } from 'vue'

// ── Mock preflight store ────────────────────────────────────────────────
const mockStatus = ref<string>('booting')
const mockProgress = ref(0)
const mockChecks = ref<any[]>([])
const mockHasFailed = ref(false)
const mockErrorMessage = ref('')
const mockRepairedItems = ref<any[]>([])
const mockAutoRepairs = ref(0)
const mockRetry = vi.fn()
const mockInstallComponent = vi.fn()

// WHY getter: Vue template 对嵌套对象不自动解包 ref，需显式 .value
vi.mock('@/stores/preflight', () => ({
  usePreFlightStore: vi.fn(() => ({
    get status() { return mockStatus.value },
    set status(v: string) { mockStatus.value = v },
    get progress() { return mockProgress.value },
    set progress(v: number) { mockProgress.value = v },
    get checks() { return mockChecks.value },
    set checks(v: any[]) { mockChecks.value = v },
    get hasFailed() { return mockHasFailed.value },
    set hasFailed(v: boolean) { mockHasFailed.value = v },
    get errorMessage() { return mockErrorMessage.value },
    set errorMessage(v: string) { mockErrorMessage.value = v },
    get repairedItems() { return mockRepairedItems.value },
    set repairedItems(v: any[]) { mockRepairedItems.value = v },
    get autoRepairs() { return mockAutoRepairs.value },
    set autoRepairs(v: number) { mockAutoRepairs.value = v },
    retry: mockRetry,
    installComponent: mockInstallComponent,
    startPolling: vi.fn(),
    stopPolling: vi.fn(),
  })),
}))
// ── End mock ─────────────────────────────────────────────────────────────

import BootScreen from '@/components/common/BootScreen.vue'

// 通用 stubs：Element Plus 组件在测试环境中无需真正渲染
const stubs = {
  'el-progress': { template: '<div class="el-progress-stub" />' },
  'el-icon': { template: '<span class="el-icon-stub"><slot /></span>' },
  'el-button': { template: '<button class="el-button-stub" @click="$emit(\'click\')"><slot /></button>' },
  Loading: { template: '<span class="loading-stub" />' },
}

describe('BootScreen', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockStatus.value = 'booting'
    mockProgress.value = 0
    mockChecks.value = []
    mockHasFailed.value = false
    mockErrorMessage.value = ''
    mockRepairedItems.value = []
    mockAutoRepairs.value = 0
  })

  it('renders title "Orbit" and subtitle', () => {
    const wrapper = mount(BootScreen, { global: { stubs } })
    expect(wrapper.text()).toContain('Orbit')
    expect(wrapper.text()).toContain('Multi-Agent Development System')
  })

  it('shows "正在连接后端..." when status is booting', () => {
    const wrapper = mount(BootScreen, { global: { stubs } })
    expect(wrapper.text()).toContain('正在连接后端')
  })

  it('shows "正在检查系统组件" when status is running', () => {
    mockStatus.value = 'running'
    const wrapper = mount(BootScreen, { global: { stubs } })
    expect(wrapper.text()).toContain('正在检查系统组件')
  })

  it('shows "所有检查通过" when status is passed', () => {
    mockStatus.value = 'passed'
    const wrapper = mount(BootScreen, { global: { stubs } })
    expect(wrapper.text()).toContain('所有检查通过')
  })

  it('renders el-progress component', () => {
    const wrapper = mount(BootScreen, { global: { stubs } })
    expect(wrapper.find('.el-progress-stub').exists()).toBe(true)
  })

  it('renders check items from preflight store', () => {
    mockChecks.value = [
      { name: 'docker', label: 'Docker', status: 'running', message: 'connecting...', auto_repaired: false, install_action: null, duration_ms: 0 },
      { name: 'git', label: 'Git', status: 'passed', message: 'ok', auto_repaired: false, install_action: null, duration_ms: 5 },
    ]
    const wrapper = mount(BootScreen, { global: { stubs } })
    expect(wrapper.findAll('.check-item').length).toBe(2)
    expect(wrapper.text()).toContain('Docker')
    expect(wrapper.text()).toContain('Git')
  })

  it('shows failed section with retry button when hasFailed', () => {
    mockStatus.value = 'failed'
    mockHasFailed.value = true
    mockErrorMessage.value = 'Docker daemon not reachable'
    const wrapper = mount(BootScreen, { global: { stubs } })
    expect(wrapper.text()).toContain('Docker daemon not reachable')
    // 重试按钮由 el-button stub 渲染
    expect(wrapper.findAll('.el-button-stub').length).toBeGreaterThanOrEqual(1)
  })

  it('shows self-heal notice when repairs exist', () => {
    mockStatus.value = 'running'
    mockAutoRepairs.value = 2
    mockRepairedItems.value = [
      { name: 'docker', label: 'Docker', message: 'restarted', auto_repaired: true },
      { name: 'sandbox', label: 'Sandbox', message: 'reinstalled', auto_repaired: true },
    ]
    const wrapper = mount(BootScreen, { global: { stubs } })
    expect(wrapper.text()).toContain('已自动修复')
    expect(wrapper.text()).toContain('Docker')
    expect(wrapper.text()).toContain('Sandbox')
  })
})
