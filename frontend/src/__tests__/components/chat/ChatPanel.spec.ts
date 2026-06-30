import { describe, it, expect, beforeEach } from 'vitest'
import { shallowMount } from '@vue/test-utils'
import { setActivePinia, createPinia } from 'pinia'
import { useChatStore } from '@/stores/chat'
import ChatPanel from '@/components/chat/ChatPanel.vue'

const global = {
  stubs: {
    'el-input': true,
    'el-button': true,
  },
}

describe('ChatPanel', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it('renders empty message list with placeholder text', () => {
    const wrapper = shallowMount(ChatPanel, { global })
    const empty = wrapper.find('.chat-panel__empty')
    expect(empty.exists()).toBe(true)
    expect(empty.text()).toContain('输入自然语言描述')
  })

  it('renders user and agent messages from store', () => {
    const store = useChatStore()
    store.messages = [
      { id: 'u1', text: '帮我分析这段代码', from: 'user', timestamp: 1000 },
      { id: 'a1', text: '好的，我来分析', from: 'agent', timestamp: 1001, role: 'clarifier' },
    ]
    const wrapper = shallowMount(ChatPanel, { global })
    const items = wrapper.findAll('.chat-msg')
    expect(items).toHaveLength(2)
    expect(items[0].text()).toContain('帮我分析这段代码')
    expect(items[0].classes()).toContain('chat-msg--user')
    expect(items[1].text()).toContain('好的，我来分析')
    expect(items[1].classes()).toContain('chat-msg--agent')
  })

  it('renders input area for typing messages', () => {
    const wrapper = shallowMount(ChatPanel, { global })
    const inputArea = wrapper.find('.chat-panel__input')
    expect(inputArea.exists()).toBe(true)
  })
})
