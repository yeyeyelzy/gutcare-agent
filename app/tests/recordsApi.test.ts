import { describe, expect, it, vi } from 'vitest'
import { RecordsApi } from '../src/api/recordsApi'
import type { RequestClient } from '../src/api/requestClient'

describe('RecordsApi', () => {
  it('uses only generated record routes, generated payloads, and idempotency headers', async () => {
    const request = vi.fn().mockResolvedValue({ items: [], next_cursor: null })
    const api = new RecordsApi({ request } as unknown as RequestClient)
    await api.list('diet-records', { limit: 30, since: '2026-10-01T00:00:00Z' })
    expect(request).toHaveBeenCalledWith({ method: 'GET', path: '/diet-records?limit=30&since=2026-10-01T00%3A00%3A00Z' })
    const body = { occurred_at: '2026-10-14T00:00:00Z', payload: { text_description: '米饭' } }
    await api.create('diet-records', body, 'dedupe-123')
    expect(request).toHaveBeenLastCalledWith({ method: 'POST', path: '/diet-records', data: body, idempotencyKey: 'dedupe-123' })
  })

  it('sends record_version on delete and reads symptom history from its dedicated endpoint', async () => {
    const request = vi.fn().mockResolvedValue(undefined)
    const api = new RecordsApi({ request } as unknown as RequestClient)
    await api.delete('stool-records', 'record-id', 4)
    expect(request).toHaveBeenCalledWith({ method: 'DELETE', path: '/stool-records/record-id?record_version=4' })
    await api.symptomStatusHistory('symptom-id')
    expect(request).toHaveBeenLastCalledWith({ method: 'GET', path: '/symptom-records/symptom-id/status-history' })
  })
})
