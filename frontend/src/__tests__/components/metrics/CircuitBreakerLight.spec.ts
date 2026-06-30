import { describe, it, expect } from 'vitest'
import { shallowMount } from '@vue/test-utils'
import CircuitBreakerLight from '@/components/metrics/CircuitBreakerLight.vue'

describe('CircuitBreakerLight', () => {
  it('renders name label', () => {
    const wrapper = shallowMount(CircuitBreakerLight, {
      props: { name: 'redis-cache', state: 0 },
    })
    expect(wrapper.find('.cb-light__label').text()).toBe('redis-cache')
    expect(wrapper.find('.cb-light').attributes('title')).toContain('redis-cache')
  })

  it('shows CLOSED state with green dot', () => {
    const wrapper = shallowMount(CircuitBreakerLight, {
      props: { name: 'db', state: 0 },
    })
    const dot = wrapper.find('.cb-light__dot')
    expect(dot.classes()).toContain('cb-light__dot--closed')
    expect(wrapper.find('.cb-light').attributes('title')).toContain('CLOSED')
  })

  it('shows OPEN state with red dot', () => {
    const wrapper = shallowMount(CircuitBreakerLight, {
      props: { name: 'db', state: 1 },
    })
    const dot = wrapper.find('.cb-light__dot')
    expect(dot.classes()).toContain('cb-light__dot--open')
    expect(wrapper.find('.cb-light').attributes('title')).toContain('OPEN')
  })

  it('shows HALF_OPEN state with yellow dot', () => {
    const wrapper = shallowMount(CircuitBreakerLight, {
      props: { name: 'db', state: 2 },
    })
    const dot = wrapper.find('.cb-light__dot')
    expect(dot.classes()).toContain('cb-light__dot--half-open')
    expect(wrapper.find('.cb-light').attributes('title')).toContain('HALF_OPEN')
  })
})
