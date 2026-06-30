import { describe, it, expect } from 'vitest'
import { shallowMount } from '@vue/test-utils'
import OutlinePanel from '@/components/editor/OutlinePanel.vue'

const items = [
  { name: 'AppComponent', kind: 'class', line: 1 },
  { name: 'render', kind: 'method', line: 10 },
  { name: 'setup', kind: 'function', line: 25 },
]

describe('OutlinePanel', () => {
  it('mounts with items prop', () => {
    const wrapper = shallowMount(OutlinePanel, { props: { items } })
    expect(wrapper.exists()).toBe(true)
    expect(wrapper.find('.outline-header').text()).toBe('Outline')
  })

  it('renders class/function/method items', () => {
    const wrapper = shallowMount(OutlinePanel, { props: { items } })
    const renderedItems = wrapper.findAll('.outline-item')
    expect(renderedItems).toHaveLength(3)
    expect(renderedItems[0].text()).toContain('AppComponent')
    expect(renderedItems[1].text()).toContain('render')
    expect(renderedItems[2].text()).toContain('setup')
  })

  it('shows empty state when items is empty', () => {
    const wrapper = shallowMount(OutlinePanel, { props: { items: [] } })
    expect(wrapper.find('.outline-empty').exists()).toBe(true)
    expect(wrapper.text()).toContain('No symbols')
  })

  it('emits select with line number on click', async () => {
    const wrapper = shallowMount(OutlinePanel, { props: { items } })
    await wrapper.findAll('.outline-item')[1].trigger('click')
    expect(wrapper.emitted('select')).toBeTruthy()
    expect(wrapper.emitted('select')![0]).toEqual([10])
  })
})
