import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import EmptyState from '@/components/common/EmptyState.vue'

// el-empty stub that renders description and slot
const ElEmptyStub = {
  props: ['description'],
  template: '<div class="el-empty-stub"><slot /><p class="el-empty__description">{{ description }}</p></div>',
}

describe('EmptyState', () => {
  it('renders description prop text', () => {
    const wrapper = mount(EmptyState, {
      props: { description: '暂无数据' },
      global: { stubs: { 'el-empty': ElEmptyStub } },
    })
    expect(wrapper.find('.empty-state').exists()).toBe(true)
    expect(wrapper.text()).toContain('暂无数据')
  })

  it('accepts and renders a different description', () => {
    const wrapper = mount(EmptyState, {
      props: { description: 'No projects found' },
      global: { stubs: { 'el-empty': ElEmptyStub } },
    })
    expect(wrapper.text()).toContain('No projects found')
  })

  it('supports default slot content inside el-empty', () => {
    const wrapper = mount(EmptyState, {
      props: { description: 'Empty' },
      slots: { default: '<button class="action-btn">New</button>' },
      global: { stubs: { 'el-empty': ElEmptyStub } },
    })
    // EmptyState template 将 slot 传给 <el-empty><slot/></el-empty>
    // el-empty stub 渲染 <slot/> → action-btn 可见
    expect(wrapper.find('.action-btn').exists()).toBe(true)
    expect(wrapper.find('.action-btn').text()).toBe('New')
  })

  it('renders with proper layout structure', () => {
    const wrapper = mount(EmptyState, {
      props: { description: 'x' },
      global: { stubs: { 'el-empty': true } },
    })
    const el = wrapper.find('.empty-state')
    expect(el.exists()).toBe(true)
  })
})
