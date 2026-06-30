import { describe, it, expect } from 'vitest'
import { shallowMount } from '@vue/test-utils'
import ChatStream from '@/components/chat/ChatStream.vue'

describe('ChatStream', () => {
  it('renders agent ID in header', () => {
    const wrapper = shallowMount(ChatStream, {
      props: { agentId: 'developer' },
    })
    expect(wrapper.text()).toContain('developer')
  })

  it('shows idle status by default', () => {
    const wrapper = shallowMount(ChatStream, {
      props: { agentId: 'reviewer' },
    })
    const badge = wrapper.find('.status-badge.idle')
    expect(badge.exists()).toBe(true)
    expect(badge.text()).toContain('空闲')
  })

  // P2-4 (PR#131): 通过 props 设置 streaming text 而非 vm 直接修改
  it('displays streaming text via streamText prop', async () => {
    const wrapper = shallowMount(ChatStream, {
      props: { agentId: 'developer', streamText: '正在生成代码...' },
    })
    await wrapper.vm.$nextTick()
    const streamBlock = wrapper.find('.streaming')
    expect(streamBlock.exists()).toBe(true)
    expect(streamBlock.text()).toContain('正在生成代码...')
  })
})
