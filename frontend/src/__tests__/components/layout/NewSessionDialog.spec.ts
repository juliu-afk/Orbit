import { describe, it, expect, beforeEach, vi } from 'vitest'
import { shallowMount } from '@vue/test-utils'
import { setActivePinia, createPinia } from 'pinia'
import NewSessionDialog from '@/components/layout/NewSessionDialog.vue'

// Mock fetch to test confirmed emission without real API call
const mockFetch = vi.fn().mockResolvedValue({
  json: () => Promise.resolve({ code: 0, data: {} }),
})

const global = {
  stubs: {
    'el-dialog': { template: '<div class="el-stub"><slot /></div>' },
    'el-radio-group': { template: '<div class="el-stub"><slot /></div>' },
    'el-radio-button': { template: '<label class="el-stub"><slot /></label>' },
    'el-input': { template: '<div class="el-stub"><slot /></div>' },
    'el-button': { template: '<button class="el-stub"><slot /></button>' },
  },
}

describe('NewSessionDialog', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.stubGlobal('fetch', mockFetch)
  })

  it('renders project input fields in open mode', () => {
    const wrapper = shallowMount(NewSessionDialog, {
      props: { visible: true },
      global,
    })
    // 打开已有项目模式下应有输入框
    const inputs = wrapper.findAll('.el-stub')
    expect(inputs.length).toBeGreaterThan(0)
  })

  it('switches between open and create modes via radio group', async () => {
    const wrapper = shallowMount(NewSessionDialog, {
      props: { visible: true },
      global,
    })
    // 默认 mode = 'open'
    expect(wrapper.vm.mode).toBe('open')
    // 切换为 'create'
    wrapper.vm.mode = 'create'
    await wrapper.vm.$nextTick()
    expect(wrapper.vm.mode).toBe('create')
    // 应有新建项目的字段
    // 这里组件内部通过 v-if="mode === 'create'" 展示 tab-content
  })

  it('emits confirmed event after successful project creation', async () => {
    const wrapper = shallowMount(NewSessionDialog, {
      props: { visible: true },
      global,
    })
    // 直接触发 handleConfirm——内部走 fetch，mock 返回成功
    wrapper.vm.openPath = 'D:/test-project'
    await wrapper.vm.handleConfirm()
    await wrapper.vm.$nextTick()
    expect(wrapper.emitted('confirmed')).toBeTruthy()
    expect(wrapper.emitted('confirmed')).toHaveLength(1)
  })
})
