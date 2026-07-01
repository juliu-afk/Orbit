import { describe, it, expect, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import SearchPanel from '@/components/editor/SearchPanel.vue'

// Mock api service
vi.mock('@/services/api', () => ({ apiGet: vi.fn() }))

describe('SearchPanel', () => {
  it('mounts successfully', () => {
    const wrapper = mount(SearchPanel, {
      global: { stubs: { 'el-dialog': true, 'el-input': true, 'el-radio-group': true, 'el-radio': true, 'el-icon': true, 'el-empty': true } }
    })
    expect(wrapper.exists()).toBe(true)
  })

  it('renders search dialog', () => {
    const wrapper = mount(SearchPanel, {
      global: { stubs: { 'el-dialog': true, 'el-input': true, 'el-radio-group': true, 'el-radio': true, 'el-icon': true, 'el-empty': true } }
    })
    expect(wrapper.findComponent({ name: 'el-dialog' }).exists()).toBe(true)
  })

  it('renders file search radio option', () => {
    const wrapper = mount(SearchPanel, {
      global: { stubs: { 'el-dialog': true, 'el-input': true, 'el-radio-group': false, 'el-radio': false, 'el-icon': true, 'el-empty': true } }
    })
    const radios = wrapper.findAllComponents({ name: 'el-radio' })
    expect(radios.length).toBeGreaterThanOrEqual(1)
  })
})
