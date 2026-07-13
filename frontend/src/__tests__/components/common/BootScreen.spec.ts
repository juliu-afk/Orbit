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

// WHY getter: Vue template 对嵌套对象不自动解包 ref
vi.mock('@/stores/preflight', () => ({
  usePreFlightStore: vi.fn(() => ({
    get status() { return mockStatus.value },
    get progress() { return mockProgress.value },
    get checks() { return mockChecks.value },
    get hasFailed() { return mockHasFailed.value },
    get errorMessage() { return mockErrorMessage.value },
    get repairedItems() { return mockRepairedItems.value },
    get autoRepairs() { return mockAutoRepairs.value },
    retry: mockRetry,
    installComponent: mockInstallComponent,
    startPolling: vi.fn(),
    stopPolling: vi.fn(),
  })),
}))
// ── End mock ─────────────────────────────────────────────────────────────

import BootScreen from '@/components/common/BootScreen.vue'

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
    const wrapper = mount(BootScreen)
    expect(wrapper.text()).toContain('Orbit')
    expect(wrapper.text()).toContain('Multi-Agent Development System')
  })

  it('shows "connecting to backend" when status is booting', () => {
    const wrapper = mount(BootScreen)
    expect(wrapper.text()).toContain('connecting to backend')
  })

  it('shows "running system checks" when status is running', () => {
    mockStatus.value = 'running'
    const wrapper = mount(BootScreen)
    expect(wrapper.text()).toContain('running system checks')
  })

  it('shows "OK all checks passed" when status is passed', () => {
    mockStatus.value = 'passed'
    const wrapper = mount(BootScreen)
    expect(wrapper.text()).toContain('OK all checks passed')
  })

  it('shows progress percentage', () => {
    mockProgress.value = 42
    const wrapper = mount(BootScreen)
    expect(wrapper.text()).toContain('42%')
  })

  it('renders check items from preflight store', () => {
    mockChecks.value = [
      { name: 'docker', label: 'Docker', status: 'running', message: 'connecting...', auto_repaired: false, install_action: null, duration_ms: 0 },
      { name: 'git', label: 'Git', status: 'passed', message: 'ok', auto_repaired: false, install_action: null, duration_ms: 5 },
    ]
    const wrapper = mount(BootScreen)
    expect(wrapper.text()).toContain('Docker')
    expect(wrapper.text()).toContain('Git')
  })

  it('shows failed section with retry button when hasFailed', () => {
    mockStatus.value = 'failed'
    mockHasFailed.value = true
    mockErrorMessage.value = 'Docker daemon not reachable'
    const wrapper = mount(BootScreen)
    expect(wrapper.text()).toContain('Docker daemon not reachable')
    expect(wrapper.text()).toContain('retry')
  })

  it('calls retry when retry button clicked', async () => {
    mockStatus.value = 'failed'
    mockHasFailed.value = true
    const wrapper = mount(BootScreen)
    const retryBtn = wrapper.find('button')
    await retryBtn.trigger('click')
    expect(mockRetry).toHaveBeenCalled()
  })

  it('shows self-heal notice when repairs exist', () => {
    mockStatus.value = 'running'
    mockAutoRepairs.value = 2
    mockRepairedItems.value = [
      { name: 'docker', label: 'Docker', message: 'restarted', auto_repaired: true },
      { name: 'sandbox', label: 'Sandbox', message: 'reinstalled', auto_repaired: true },
    ]
    const wrapper = mount(BootScreen)
    expect(wrapper.text()).toContain('auto-repaired')
    expect(wrapper.text()).toContain('Docker')
    expect(wrapper.text()).toContain('Sandbox')
  })
})
