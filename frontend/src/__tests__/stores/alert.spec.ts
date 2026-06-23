import { describe, it, expect, beforeEach } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import { useAlertStore } from '@/stores/alert'
import type { Alert } from '@/types/dashboard'

function makeAlert(taskId: string, message: string): Alert {
  return {
    task_id: taskId,
    level: 'l3_entropy',
    severity: 'warning',
    message,
    timestamp: new Date().toISOString(),
  }
}

describe('Alert Store', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it('初始无告警', () => {
    const store = useAlertStore()
    expect(store.alerts).toHaveLength(0)
  })

  it('addAlert 插入顶部', () => {
    const store = useAlertStore()
    store.addAlert(makeAlert('t1', 'msg-1'))
    store.addAlert(makeAlert('t2', 'msg-2'))
    expect(store.alerts).toHaveLength(2)
    expect(store.alerts[0].message).toBe('msg-2') // 最新在顶部
  })

  it('超过 20 条时 pop 最旧', () => {
    const store = useAlertStore()
    for (let i = 0; i < 22; i++) {
      store.addAlert(makeAlert(`t${i}`, `msg-${i}`))
    }
    expect(store.alerts).toHaveLength(20)
    expect(store.alerts[0].message).toBe('msg-21')   // 最新
    expect(store.alerts[19].message).toBe('msg-2')   // 最旧（msg-0, msg-1 被 pop）
  })

  it('clearAlerts 清空', () => {
    const store = useAlertStore()
    store.addAlert(makeAlert('t1', 'msg'))
    store.clearAlerts()
    expect(store.alerts).toHaveLength(0)
  })
})
