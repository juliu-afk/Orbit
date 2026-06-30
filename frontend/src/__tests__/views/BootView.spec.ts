import { describe, it, expect, vi, beforeEach } from 'vitest'
import { shallowMount } from '@vue/test-utils'
import { ref } from 'vue'

// ── Mocks ────────────────────────────────────────────────────────────────

const mockPush = vi.fn()
vi.mock('vue-router', () => ({
  useRouter: vi.fn(() => ({ push: mockPush })),
}))

const mockStatus = ref<string>('booting')
const mockStartPolling = vi.fn()
const mockStopPolling = vi.fn()

vi.mock('@/stores/preflight', () => ({
  usePreFlightStore: vi.fn(() => ({
    status: mockStatus,
    startPolling: mockStartPolling,
    stopPolling: mockStopPolling,
  })),
}))

// ── End mocks ────────────────────────────────────────────────────────────

import BootView from '@/views/BootView.vue'

describe('BootView', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockStatus.value = 'booting'
  })

  it('renders BootScreen component (stubbed by shallowMount)', () => {
    const wrapper = shallowMount(BootView)
    // shallowMount stubs child components — BootScreen stub should be present
    expect(wrapper.findComponent({ name: 'BootScreen' }).exists()).toBe(true)
  })

  it('calls preflight.startPolling() on mount', () => {
    shallowMount(BootView)
    expect(mockStartPolling).toHaveBeenCalledOnce()
  })

  it('does NOT call startPolling before mount', () => {
    expect(mockStartPolling).not.toHaveBeenCalled()
  })

  it('calls preflight.stopPolling() on unmount', () => {
    const wrapper = shallowMount(BootView)
    expect(mockStopPolling).not.toHaveBeenCalled()
    wrapper.unmount()
    expect(mockStopPolling).toHaveBeenCalledOnce()
  })

  it('triggers router.push to dashboard when status becomes "passed"', async () => {
    vi.useFakeTimers()
    shallowMount(BootView)

    mockStatus.value = 'passed'
    // Vue watch 触发后 setTimeout(600ms)
    await vi.advanceTimersByTimeAsync(700)

    expect(mockPush).toHaveBeenCalledWith({ name: 'dashboard' })
    vi.useRealTimers()
  })

  it('does NOT navigate when status is not "passed"', async () => {
    vi.useFakeTimers()
    shallowMount(BootView)

    mockStatus.value = 'running'
    await vi.advanceTimersByTimeAsync(700)
    expect(mockPush).not.toHaveBeenCalled()

    mockStatus.value = 'failed'
    await vi.advanceTimersByTimeAsync(700)
    expect(mockPush).not.toHaveBeenCalled()

    vi.useRealTimers()
  })
})
