import { describe, it, expect } from 'vitest'
import { shallowMount } from '@vue/test-utils'
import ProblemPanel from '@/components/editor/ProblemPanel.vue'
import type { Diagnostic } from '@/stores/diagnostics'

const diagnostics: Diagnostic[] = [
  {
    filePath: 'src/app.ts',
    line: 10,
    column: 5,
    severity: 'error',
    message: 'Type mismatch',
    ruleId: 'TS2322',
  },
  {
    filePath: 'src/utils.ts',
    line: 42,
    column: 3,
    severity: 'warning',
    message: 'Unused variable',
    ruleId: null,
  },
]

describe('ProblemPanel', () => {
  it('mounts with diagnostics prop', () => {
    const wrapper = shallowMount(ProblemPanel, { props: { diagnostics } })
    expect(wrapper.exists()).toBe(true)
  })

  it('renders each diagnostic as a problem-item', () => {
    const wrapper = shallowMount(ProblemPanel, { props: { diagnostics } })
    expect(wrapper.findAll('.problem-item')).toHaveLength(2)
  })

  it('shows empty state when diagnostics is empty', () => {
    const wrapper = shallowMount(ProblemPanel, { props: { diagnostics: [] } })
    expect(wrapper.find('.no-problems').exists()).toBe(true)
    expect(wrapper.text()).toContain('No issues')
  })

  it('displays severity icon, file:line, and message', () => {
    const wrapper = shallowMount(ProblemPanel, { props: { diagnostics } })
    const first = wrapper.find('.problem-item')
    expect(first.find('.severity-icon').exists()).toBe(true)
    expect(first.text()).toContain('app.ts:10')
    expect(first.text()).toContain('Type mismatch')
  })

  it('shows ruleId badge when present', () => {
    const wrapper = shallowMount(ProblemPanel, { props: { diagnostics } })
    expect(wrapper.find('.problem-rule').exists()).toBe(true)
    expect(wrapper.find('.problem-rule').text()).toBe('TS2322')
  })

  it('emits click with diagnostic data on item click', async () => {
    const wrapper = shallowMount(ProblemPanel, { props: { diagnostics } })
    await wrapper.findAll('.problem-item')[0].trigger('click')
    expect(wrapper.emitted('click')).toBeTruthy()
    expect(wrapper.emitted('click')![0][0]).toEqual(diagnostics[0])
  })
})
