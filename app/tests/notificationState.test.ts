import { describe, expect, it } from 'vitest'
import type { PatientNotification } from '../src/api/openapiTypes'
import { applyNotificationRead, NotificationFirstShowGate, unreadCountAfterUpdates } from '../src/api/notificationState'

const item = (id: string, read_at: string | null = null): PatientNotification => ({
  id, event_type: 'risk_alert_created', category: 'risk', priority: 'risk', occurred_at: '2026-10-18T00:00:00Z', created_at: '2026-10-18T00:00:00Z', read_at,
  target: { type: 'risk_alert', id: '00000000-0000-4000-8000-000000000001' }, target_unavailable: false,
})

describe('F12 client state helpers', () => {
  it('skips duplicate first onShow reload but refreshes after returning from detail', () => {
    const gate = new NotificationFirstShowGate()
    expect(gate.shouldRefresh()).toBe(false)
    expect(gate.shouldRefresh()).toBe(true)
    expect(gate.shouldRefresh()).toBe(true)
  })

  it('updates only exact server-returned notifications and decrements unread count by newly-read selected rows', () => {
    const rows = [item('a'), item('b'), item('c', '2026-10-17T00:00:00Z')]
    const returned = [item('a', '2026-10-18T01:00:00Z')]
    expect(applyNotificationRead(rows, returned)).toEqual([returned[0], rows[1], rows[2]])
    expect(unreadCountAfterUpdates(4, rows, returned)).toBe(3)
    expect(unreadCountAfterUpdates(0, rows, returned)).toBe(0)
  })
})
