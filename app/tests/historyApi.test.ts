import { describe, expect, it, vi } from 'vitest'
import { HistoryApi } from '../src/api/historyApi'
import type { RequestClient } from '../src/api/requestClient'

describe('HistoryApi', () => {
  it('sends generated timeline filters with repeated allow-listed category parameters', async () => {
    const request = vi.fn().mockResolvedValue({ items: [], next_cursor: null })
    const api = new HistoryApi({ request } as unknown as RequestClient)
    await api.list({
      limit: 20, cursor: 'signed cursor', category: ['mood', 'diet', 'mood'],
      since: '2026-03-08T05:00:00.000Z', until: '2026-03-09T04:00:00.000Z',
    })
    expect(request).toHaveBeenCalledWith({
      method: 'GET',
      path: '/history/timeline?limit=20&cursor=signed+cursor&category=diet&category=mood&since=2026-03-08T05%3A00%3A00.000Z&until=2026-03-09T04%3A00%3A00.000Z',
    })
  })

  it('does not invent patient identifiers or send category when no filters are selected', async () => {
    const request = vi.fn().mockResolvedValue({ items: [], next_cursor: null })
    const api = new HistoryApi({ request } as unknown as RequestClient)
    await api.list({ limit: 20 })
    expect(request).toHaveBeenCalledWith({ method: 'GET', path: '/history/timeline?limit=20' })
    expect(JSON.stringify(request.mock.calls)).not.toContain('patient_id')
  })
})
