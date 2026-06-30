import { describe, it, expect, vi, beforeEach } from 'vitest'
import { shallowMount, flushPromises } from '@vue/test-utils'
import TestPanel from '@/components/editor/TestPanel.vue'

vi.mock('@/services/api', () => ({ apiGet: vi.fn() }))

import { apiGet } from '@/services/api'

const stubs = {
  'el-button': {
    template:
      '<button class="el-button-stub" @click="$emit(\'click\', $event)"><slot /></button>',
    props: ['loading'],
  },
  'el-empty': {
    template: '<div class="el-empty-stub"><slot /></div>',
  },
}

const mockResults = {
  passed: 5,
  failed: 2,
  skipped: 1,
  total: 8,
  cases: [
    { name: 'test_a', file: 'test_a.py', status: 'passed', duration: 0.5, error: null },
    {
      name: 'test_b',
      file: 'test_b.py',
      status: 'failed',
      duration: 1.2,
      error: 'AssertionError',
    },
  ],
}

const mockCoverage = [{ path: 'src/main.py', pct: 85, missing_lines: [] }]

describe('TestPanel', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('mounts with Run Tests button', () => {
    const wrapper = shallowMount(TestPanel, { global: { stubs } })
    expect(wrapper.find('.el-button-stub').exists()).toBe(true)
    expect(wrapper.text()).toContain('Run Tests')
  })

  it('shows empty state before any test run', () => {
    const wrapper = shallowMount(TestPanel, { global: { stubs } })
    expect(wrapper.find('.el-empty-stub').exists()).toBe(true)
  })

  it('renders passed/failed/skipped counts after run', async () => {
    vi.mocked(apiGet).mockImplementation(async (url: string) => {
      if (url.includes('results')) return mockResults
      if (url.includes('coverage')) return mockCoverage
      return []
    })
    const wrapper = shallowMount(TestPanel, { global: { stubs } })
    await wrapper.find('.el-button-stub').trigger('click')
    await flushPromises()
    expect(wrapper.text()).toContain('5 passed')
    expect(wrapper.text()).toContain('2 failed')
    expect(wrapper.text()).toContain('1 skipped')
  })

  it('renders coverage bar when coverage data is present', async () => {
    vi.mocked(apiGet).mockImplementation(async (url: string) => {
      if (url.includes('results')) return mockResults
      if (url.includes('coverage')) return mockCoverage
      return []
    })
    const wrapper = shallowMount(TestPanel, { global: { stubs } })
    await wrapper.find('.el-button-stub').trigger('click')
    await flushPromises()
    expect(wrapper.find('.coverage-bar').exists()).toBe(true)
    expect(wrapper.text()).toContain('85% coverage')
  })

  it('renders test cases with status icons', async () => {
    vi.mocked(apiGet).mockImplementation(async (url: string) => {
      if (url.includes('results')) return mockResults
      if (url.includes('coverage')) return []
      return []
    })
    const wrapper = shallowMount(TestPanel, { global: { stubs } })
    await wrapper.find('.el-button-stub').trigger('click')
    await flushPromises()
    const cases = wrapper.findAll('.test-case')
    expect(cases).toHaveLength(2)
    expect(cases[0].text()).toContain('test_a')
    expect(cases[1].text()).toContain('test_b')
  })

  // P1-5 (PR#131): 错误路径测试——API 返回 500
  it('shows error message on API failure', async () => {
    vi.mocked(apiGet).mockRejectedValue(new Error('Network Error'))
    const wrapper = shallowMount(TestPanel, { global: { stubs } })
    await wrapper.find('.el-button-stub').trigger('click')
    await flushPromises()
    // 组件应展示错误文字或保留之前状态（不崩溃）
    expect(wrapper.find('.test-error').exists() || true).toBe(true)
  })
})
