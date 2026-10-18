import { describe, expect, it, vi } from 'vitest'
import { AdviceApi } from '../src/api/adviceApi'
import type { RequestClient } from '../src/api/requestClient'

describe('AdviceApi', () => {
  it('uses generated patient endpoints, stable cursor parameters and encoded ids', async () => {
    const request = vi.fn().mockResolvedValue({ items: [], next_cursor: null })
    const api = new AdviceApi({ request } as unknown as RequestClient)
    await api.list({ limit: 20, cursor: 'cursor/value' })
    expect(request).toHaveBeenCalledWith({ method: 'GET', path: '/advice?limit=20&cursor=cursor%2Fvalue' })
    await api.get('advice/id')
    await api.markRead('advice/id')
    await api.archive('advice/id')
    expect(request).toHaveBeenNthCalledWith(2, { method: 'GET', path: '/advice/advice%2Fid' })
    expect(request).toHaveBeenNthCalledWith(3, { method: 'POST', path: '/advice/advice%2Fid/read' })
    expect(request).toHaveBeenNthCalledWith(4, { method: 'POST', path: '/advice/advice%2Fid/archive' })
  })

  it('binds feedback to expected version and explicit idempotency key', async () => {
    const request = vi.fn().mockResolvedValue({ advice_id: 'a', feedback_type: 'helpful', version: 1 })
    const api = new AdviceApi({ request } as unknown as RequestClient)
    await api.feedback('id', { feedback_type: 'helpful', expected_version: 0 }, 'advice-feedback-test-key')
    expect(request).toHaveBeenCalledWith({
      method: 'PUT', path: '/advice/id/feedback',
      data: { feedback_type: 'helpful', expected_version: 0 }, idempotencyKey: 'advice-feedback-test-key',
    })
  })
})
