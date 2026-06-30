import { describe, it, expect, beforeEach } from 'vitest'
import { shallowMount } from '@vue/test-utils'
import { setActivePinia, createPinia } from 'pinia'
import HealthPanel from '@/components/metrics/HealthPanel.vue'
import type { ComponentHealth } from '@/types/dashboard'

const healthyComponents: ComponentHealth[] = [
  { name: 'API Server', status: 'healthy', message: '', metrics: {} },
  { name: 'Database', status: 'healthy', message: '', metrics: {} },
]

const degradedComponents: ComponentHealth[] = [
  { name: 'Redis', status: 'degraded', message: 'latency high', metrics: {} },
]

describe('HealthPanel', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it('renders component items with name and status', () => {
    const wrapper = shallowMount(HealthPanel, {
      props: { components: healthyComponents, overall: 'healthy' },
    })
    const items = wrapper.findAll('.health-panel__item')
    expect(items).toHaveLength(2)
    expect(items[0].text()).toContain('API Server')
    expect(items[1].text()).toContain('Database')
  })

  it('shows healthy overall status label in Chinese', () => {
    const wrapper = shallowMount(HealthPanel, {
      props: { components: healthyComponents, overall: 'healthy' },
    })
    const overall = wrapper.find('.health-panel__overall')
    expect(overall.text()).toContain('健康')
    expect(overall.find('.health-panel__overall--healthy').exists()).toBe(true)
  })

  it('handles degraded overall status', () => {
    const wrapper = shallowMount(HealthPanel, {
      props: { components: degradedComponents, overall: 'degraded' },
    })
    const overall = wrapper.find('.health-panel__overall')
    expect(overall.text()).toContain('降级')
    expect(overall.find('.health-panel__overall--degraded').exists()).toBe(true)
    const item = wrapper.find('.health-panel__item')
    expect(item.exists()).toBe(true)
  })
})
