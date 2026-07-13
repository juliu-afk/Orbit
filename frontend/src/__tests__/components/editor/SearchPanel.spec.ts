import { describe, it, expect, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import SearchPanel from '@/components/editor/SearchPanel.vue'

// Mock api service
vi.mock('@/services/api', () => ({ apiGet: vi.fn() }))

// WHY all-stub: Element Plus 组件在 vitest jsdom 中不全局注册，全部 stub
const stubs = {
  'el-dialog': { template: '<div class="el-dialog-stub"><slot /></div>' },
  'el-input': { template: '<input class="el-input-stub" />' },
  'el-radio-group': { template: '<div class="el-radio-group-stub"><slot /></div>' },
  'el-radio': { template: '<label class="el-radio-stub"><slot /></label>' },
  'el-icon': { template: '<span class="el-icon-stub" />' },
  'el-empty': { template: '<div class="el-empty-stub" />' },
  'el-button': { template: '<button class="el-button-stub"><slot /></button>' },
}

describe('SearchPanel', () => {
  it('mounts successfully', () => {
    const wrapper = mount(SearchPanel, { global: { stubs } })
    expect(wrapper.exists()).toBe(true)
  })

  it('renders search dialog', () => {
    const wrapper = mount(SearchPanel, { global: { stubs } })
    expect(wrapper.find('.el-dialog-stub').exists()).toBe(true)
  })

  it('renders file search radio option', () => {
    const wrapper = mount(SearchPanel, { global: { stubs } })
    // el-radio stubs 都会渲染为 .el-radio-stub
    const radios = wrapper.findAll('.el-radio-stub')
    expect(radios.length).toBeGreaterThanOrEqual(1)
  })
})
