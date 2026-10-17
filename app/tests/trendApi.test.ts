import { describe, expect, it, vi } from 'vitest'
import { TrendApi } from '../src/api/trendApi'
import type { RequestClient } from '../src/api/requestClient'

describe('TrendApi', () => {
  it('uses the shared request client and serializes timezone-aware half-open bounds and bucket', async () => {
    const request = vi.fn().mockResolvedValue({})
    const api = new TrendApi({ request } as unknown as RequestClient)
    await api.get({ from: '2026-03-08T05:00:00.000Z', to: '2026-03-09T04:00:00.000Z', bucket: 'week' })
    expect(request).toHaveBeenCalledWith({
      method: 'GET',
      path: '/trends?from=2026-03-08T05%3A00%3A00.000Z&to=2026-03-09T04%3A00%3A00.000Z&bucket=week',
    })
  })
})
