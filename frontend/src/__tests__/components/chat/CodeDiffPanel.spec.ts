import { describe, it, expect } from 'vitest'
import { shallowMount } from '@vue/test-utils'
import CodeDiffPanel from '@/components/chat/CodeDiffPanel.vue'

describe('CodeDiffPanel', () => {
  it('renders code prop in pre/code element', () => {
    const code = 'def hello():\n    print("world")'
    const wrapper = shallowMount(CodeDiffPanel, {
      props: { code },
    })
    const pre = wrapper.find('.code-diff-panel__pre')
    expect(pre.exists()).toBe(true)
    expect(pre.text()).toContain('def hello()')
    expect(pre.text()).toContain('print')
  })

  it('handles empty code string', () => {
    const wrapper = shallowMount(CodeDiffPanel, {
      props: { code: '' },
    })
    const pre = wrapper.find('.code-diff-panel__pre')
    expect(pre.exists()).toBe(true)
    expect(pre.text()).toBe('')
  })
})
