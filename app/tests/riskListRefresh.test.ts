import { describe, expect, it } from 'vitest'
import { RiskListFirstShowGate, safeRefreshRiskList } from '../src/api/riskListRefresh'
import type { RiskAlert, RiskAlertPage } from '../src/api/openapiTypes'

const unreadAlert: RiskAlert = {
  id: '00000000-0000-4000-8000-000000000001', severity: 'emergency', message: '提示', recommended_action: '立即查看行动建议',
  status: 'unread', triggered_at: '2026-10-18T00:00:00Z', read_at: null, reevaluated_at: null, evidence: {},
}

describe('risk list resume refresh', () => {
  it('skips the first onShow because onLoad already starts the initial request, then refreshes later shows', () => {
    const gate = new RiskListFirstShowGate()
    expect(gate.shouldFetch()).toBe(false)
    expect(gate.shouldFetch()).toBe(true)
  })

  it('replaces stale unread state with the server state after a detail action returns', async () => {
    const current = { items: [unreadAlert], cursor: 'old-cursor' }
    const afterDetailAction: RiskAlertPage = { items: [{ ...unreadAlert, status: 'read' }], next_cursor: null }
    const result = await safeRefreshRiskList(current, async () => afterDetailAction)
    expect(result.snapshot.items[0]?.status).toBe('read')
    expect(result.snapshot.cursor).toBeNull()
    expect(result.error).toBeNull()
  })

  it('keeps the last good items/cursor and returns an error for visible retry UI', async () => {
    const current = { items: [unreadAlert], cursor: 'keep-cursor' }
    const result = await safeRefreshRiskList(current, async () => { throw new Error('offline') })
    expect(result.snapshot).toBe(current)
    expect(result.snapshot.items).toEqual([unreadAlert])
    expect(result.snapshot.cursor).toBe('keep-cursor')
    expect(result.error).toBeInstanceOf(Error)
  })
})
