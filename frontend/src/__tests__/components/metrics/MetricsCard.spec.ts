import { describe, it, expect } from 'vitest'
import { shallowMount } from '@vue/test-utils'
import MetricsCard from '@/components/metrics/MetricsCard.vue'

describe('MetricsCard', () => {
  it('renders title and numeric value', () => {
    const wrapper = shallowMount(MetricsCard, {
      props: { title: '总任务数', value: 42 },
    })
    expect(wrapper.find('.metrics-card__title').text()).toBe('总任务数')
    expect(wrapper.find('.metrics-card__value').text()).toContain('42')
  })

  it('shows unit suffix next to value', () => {
    const wrapper = shallowMount(MetricsCard, {
      props: { title: '响应时间', value: 230, unit: 'ms' },
    })
    expect(wrapper.find('.metrics-card__value').text()).toContain('230')
    expect(wrapper.find('.metrics-card__unit').text()).toBe('ms')
  })

  it('shows trend indicator with arrow and percentage (P2-3: 后续拆分为up/down独立测试)', () => {
    const wrapper = shallowMount(MetricsCard, {
      props: { title: '错误率', value: 5, trend: 12 },
    })
    const trend = wrapper.find('.metrics-card__trend')
    expect(trend.exists()).toBe(true)
    expect(trend.classes()).toContain('metrics-card__trend--up')
    expect(trend.text()).toContain('↑')
    expect(trend.text()).toContain('12')

    const downWrapper = shallowMount(MetricsCard, {
      props: { title: '错误率', value: 5, trend: -8 },
    })
    const downTrend = downWrapper.find('.metrics-card__trend')
    expect(downTrend.classes()).toContain('metrics-card__trend--down')
    expect(downTrend.text()).toContain('↓')
    expect(downTrend.text()).toContain('8')
  })

  it('shows loading state with dashes', () => {
    const wrapper = shallowMount(MetricsCard, {
      props: { title: 'CPU', value: null, loading: true },
    })
    expect(wrapper.find('.metrics-card').classes()).toContain('metrics-card--loading')
    expect(wrapper.find('.metrics-card__value').text()).toContain('---')
    expect(wrapper.find('.metrics-card__unit').exists()).toBe(false)
  })
})
