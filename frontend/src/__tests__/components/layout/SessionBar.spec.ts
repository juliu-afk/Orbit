import { describe, it, expect, beforeEach, vi } from 'vitest'
import { shallowMount } from '@vue/test-utils'
import { setActivePinia, createPinia } from 'pinia'
import { useSessionStore } from '@/stores/session'

vi.mock('@tauri-apps/api/window', () => ({
  getCurrentWindow: () => ({ minimize: vi.fn(), close: vi.fn() }),
}))

import SessionBar from '@/components/layout/SessionBar.vue'

const global = {
  stubs: {
    'el-dropdown': { template: '<div class="el-stub"><slot /></div>' },
    'el-dropdown-menu': true,
    'el-dropdown-item': true,
    'el-icon': { template: '<i class="el-stub"><slot /></i>' },
    'el-button': { template: '<button class="el-stub"><slot /></button>' },
  },
}

describe('SessionBar', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it('renders project name badge when project is set', () => {
    const store = useSessionStore()
    store.currentProjectName = 'my-project'
    const wrapper = shallowMount(SessionBar, { global })
    const badge = wrapper.find('.project-badge')
    expect(badge.exists()).toBe(true)
    expect(badge.text()).toContain('my-project')
  })

  it('shows session dropdown trigger when sessions exist', () => {
    const store = useSessionStore()
    store.sessions = [
      { session_id: 's1', project_name: 'p1', local_path: '', title: 'Session 1', status: 'active', created_at: 100, updated_at: 100 },
    ]
    store.currentTitle = 'Session 1'
    const wrapper = shallowMount(SessionBar, { global })
    const trigger = wrapper.find('.session-dropdown-trigger')
    expect(trigger.exists()).toBe(true)
    expect(trigger.text()).toContain('Session 1')
  })

  it('emits new-session event when button is clicked', async () => {
    const wrapper = shallowMount(SessionBar, { global })
    const btn = wrapper.find('.el-stub')
    await btn.trigger('click')
    expect(wrapper.emitted('new-session')).toBeTruthy()
  })
})
