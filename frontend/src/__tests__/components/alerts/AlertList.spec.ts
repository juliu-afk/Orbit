import { describe, it, expect, beforeEach } from 'vitest'
import { shallowMount } from '@vue/test-utils'
import { setActivePinia, createPinia } from 'pinia'
import { useAlertStore } from '@/stores/alert'
import AlertList from '@/components/alerts/AlertList.vue'
import type { Alert } from '@/types/dashboard'

const global = {
  stubs: {
    'el-empty': { template: '<div class="el-stub-empty"><slot /></div>' },
    'el-table': { template: '<div class="el-stub-table"><slot /></div>' },
    'el-table-column': true,
    'el-tag': { template: '<span class="el-stub-tag"><slot /></span>' },
    'el-button': { template: '<button class="el-stub"><slot /></button>' },
  },
}

function makeAlert(taskId: string, message: string, severity: 'warning' | 'critical' = 'warning'): Alert {
  return {
    task_id: taskId,
    level: 'l3_entropy',
    severity,
    message,
    timestamp: new Date().toISOString(),
  }
}

describe('AlertList', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  // P0-3 (PR#131): 移除 .skip——空状态测试应正常验证
  it('shows empty state when no alerts', () => {
    const wrapper = shallowMount(AlertList, { global })
    const empty = wrapper.find('.el-stub-empty')
    expect(empty.exists()).toBe(true)
    expect(wrapper.text()).toContain('无告警')
  })

  it('renders alert items from store', () => {
    const store = useAlertStore()
    store.addAlert(makeAlert('t1', 'CPU 使用率过高', 'warning'))
    store.addAlert(makeAlert('t2', '数据库连接超时', 'critical'))

    const wrapper = shallowMount(AlertList, { global })
    // el-table-column stubs render minimal content, so check for message text indirectly
    expect(wrapper.find('.el-stub-table').exists()).toBe(true)
    expect(wrapper.find('.el-stub-empty').exists()).toBe(false)
    expect(store.alerts).toHaveLength(2)
  })

  it('clears alerts via clear button', async () => {
    const store = useAlertStore()
    store.addAlert(makeAlert('t1', 'test alert'))
    expect(store.alerts).toHaveLength(1)

    const wrapper = shallowMount(AlertList, { global })
    const clearBtn = wrapper.find('.el-stub')
    await clearBtn.trigger('click')

    // 内部调用 alertStore.clearAlerts()
    expect(store.alerts).toHaveLength(0)
  })
})
