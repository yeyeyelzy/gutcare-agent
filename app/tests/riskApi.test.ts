import { describe, expect, it, vi } from 'vitest'
import { RiskApi } from '../src/api/riskApi'
import type { RequestClient } from '../src/api/requestClient'

describe('RiskApi', () => {
  it('uses generated F10 endpoints, cursor pagination and unread filter', async () => {
    const request = vi.fn().mockResolvedValue({ items: [], next_cursor: null })
    const api = new RiskApi({ request } as unknown as RequestClient)
    await api.list({ limit: 20, cursor: 'next', unread_only: true })
    expect(request).toHaveBeenCalledWith({ method: 'GET', path: '/risk-alerts?limit=20&cursor=next&unread_only=true' })
    await api.get('alert/id')
    expect(request).toHaveBeenLastCalledWith({ method: 'GET', path: '/risk-alerts/alert%2Fid' })
  })

  it('keeps read and reevaluate as separate actions with distinct endpoints', async () => {
    const request = vi.fn().mockResolvedValue({ id: 'alert-id', status: 'read' })
    const api = new RiskApi({ request } as unknown as RequestClient)
    await api.markRead('alert-id')
    expect(request).toHaveBeenLastCalledWith({ method: 'POST', path: '/risk-alerts/alert-id/read' })
    await api.reevaluate('alert-id')
    expect(request).toHaveBeenLastCalledWith({ method: 'POST', path: '/risk-alerts/alert-id/reevaluate' })
  })
})
