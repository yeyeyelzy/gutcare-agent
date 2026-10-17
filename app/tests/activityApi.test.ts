import { describe, expect, it, vi } from 'vitest'
import { ActivityApi } from '../src/api/activityApi'
import type { RequestClient } from '../src/api/requestClient'

describe('ActivityApi', () => {
  it('uses generated F07 routes and cursor query without inventing create idempotency semantics', async () => {
    const request = vi.fn().mockResolvedValue({ items: [], next_cursor: null })
    const api = new ActivityApi({ request } as unknown as RequestClient)
    await api.list({ limit: 30, cursor: 'next', since: '2026-10-01T00:00:00Z' })
    expect(request).toHaveBeenCalledWith({ method: 'GET', path: '/activity-records?limit=30&cursor=next&since=2026-10-01T00%3A00%3A00Z' })
    const body = { activity_type: 'other' as const, description: '散步', intensity: 'low' as const, subjective_feeling: 'same' as const, duration_minutes: 45, occurred_at: '2026-10-18T01:30:00Z' }
    await api.create(body)
    expect(request).toHaveBeenLastCalledWith({ method: 'POST', path: '/activity-records', data: body })
    expect(request.mock.calls[1]?.[0]).not.toHaveProperty('idempotencyKey')
  })

  it('uses record_version for PATCH/DELETE and encodes detail identifiers', async () => {
    const request = vi.fn().mockResolvedValue(undefined)
    const api = new ActivityApi({ request } as unknown as RequestClient)
    await api.get('activity/id')
    expect(request).toHaveBeenLastCalledWith({ method: 'GET', path: '/activity-records/activity%2Fid' })
    const patch = { record_version: 4, duration_minutes: 60 }
    await api.update('activity-id', patch)
    expect(request).toHaveBeenLastCalledWith({ method: 'PATCH', path: '/activity-records/activity-id', data: patch })
    await api.delete('activity-id', 5)
    expect(request).toHaveBeenLastCalledWith({ method: 'DELETE', path: '/activity-records/activity-id', data: { record_version: 5 } })
  })
})
