import { describe, expect, it, vi } from 'vitest'
import { MoodApi } from '../src/api/moodApi'
import type { RequestClient } from '../src/api/requestClient'

describe('MoodApi', () => {
  it('uses generated mood routes, DTO payloads and the exact create idempotency key', async () => {
    const request = vi.fn().mockResolvedValue({ items: [], next_cursor: null })
    const api = new MoodApi({ request } as unknown as RequestClient)
    await api.list({ limit: 30, cursor: 'cursor', since: '2026-10-01T00:00:00Z' })
    expect(request).toHaveBeenCalledWith({ method: 'GET', path: '/mood-records?limit=30&cursor=cursor&since=2026-10-01T00%3A00%3A00Z' })
    const body = { occurred_at: '2026-10-18T01:30:00Z', mood_level: 4, emotion_tags: [], note: 'private' }
    await api.create(body, 'idem-key')
    expect(request).toHaveBeenLastCalledWith({ method: 'POST', path: '/mood-records', data: body, idempotencyKey: 'idem-key' })
  })

  it('uses record_version on PATCH and DELETE and encodes detail identifiers', async () => {
    const request = vi.fn().mockResolvedValue(undefined)
    const api = new MoodApi({ request } as unknown as RequestClient)
    await api.get('mood/id')
    expect(request).toHaveBeenLastCalledWith({ method: 'GET', path: '/mood-records/mood%2Fid' })
    const patch = { record_version: 3, occurred_at: '2026-10-18T01:30:00Z', mood_level: 2, emotion_tags: [], note: null }
    await api.update('mood-id', patch)
    expect(request).toHaveBeenLastCalledWith({ method: 'PATCH', path: '/mood-records/mood-id', data: patch })
    await api.delete('mood-id', 4)
    expect(request).toHaveBeenLastCalledWith({ method: 'DELETE', path: '/mood-records/mood-id', data: { record_version: 4 } })
  })
})
