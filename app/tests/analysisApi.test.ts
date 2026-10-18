import { describe, expect, it, vi } from 'vitest'
import { AnalysisApi } from '../src/api/analysisApi'
import type { RequestClient } from '../src/api/requestClient'

const id = '00000000-0000-4000-8000-000000000001'
const body = { analysis_type: 'comprehensive_health_analysis' as const, requested_from: null, requested_to: null }
const task = { id, analysis_type: body.analysis_type, status: 'pending' as const, input_summary: { included_mood_record_count: 0 }, created_at: '2026-10-01T00:00:00Z', updated_at: '2026-10-01T00:00:00Z', attempt: 1, retry_of: null, result: null, error_code: null }

describe('AnalysisApi', () => {
  it('uses generated preview/list/detail contract with encoded UTC scope and opaque cursor', async () => {
    const request = vi.fn().mockResolvedValueOnce({}).mockResolvedValueOnce({ items: [task], next_cursor: null }).mockResolvedValueOnce(task)
    const api = new AnalysisApi({ request } as unknown as RequestClient)
    await api.preview({ ...body, requested_from: '2026-10-01T00:00:00Z', requested_to: '2026-10-08T00:00:00Z' })
    await api.list({ limit: 20, cursor: 'opaque+cursor' })
    await api.get(id)
    expect(request.mock.calls.map(([arg]) => arg.path)).toEqual([
      '/analysis-tasks/preview?analysis_type=comprehensive_health_analysis&requested_from=2026-10-01T00%3A00%3A00Z&requested_to=2026-10-08T00%3A00%3A00Z',
      '/analysis-tasks?limit=20&cursor=opaque%2Bcursor',
      `/analysis-tasks/${id}`,
    ])
  })

  it('posts a generated request with idempotency key and requires the 202 Location to match the returned task', async () => {
    const requestWithMetadata = vi.fn().mockResolvedValue({ status: 202, data: task, headers: { Location: `/api/v1/analysis-tasks/${id}` } })
    const api = new AnalysisApi({ requestWithMetadata } as unknown as RequestClient)
    await expect(api.create(body, 'analysis-test-idem-001')).resolves.toEqual({ task, location: `/api/v1/analysis-tasks/${id}` })
    expect(requestWithMetadata).toHaveBeenCalledWith({ method: 'POST', path: '/analysis-tasks', data: body, idempotencyKey: 'analysis-test-idem-001' })
  })

  it('fails closed on missing or mismatched Location metadata', async () => {
    const requestWithMetadata = vi.fn().mockResolvedValue({ status: 202, data: task, headers: { Location: '/analysis-tasks/00000000-0000-4000-8000-000000000099' } })
    const api = new AnalysisApi({ requestWithMetadata } as unknown as RequestClient)
    await expect(api.create(body, 'analysis-test-idem-002')).rejects.toThrow('Location')
  })

  it('retries a failed task with an idempotency key and validates Location plus retry_of', async () => {
    const retried = { ...task, id: '00000000-0000-4000-8000-000000000002', status: 'pending' as const, attempt: 2, retry_of: id }
    const requestWithMetadata = vi.fn().mockResolvedValue({ status: 202, data: retried, headers: { Location: `/api/v1/analysis-tasks/${retried.id}` } })
    const api = new AnalysisApi({ requestWithMetadata } as unknown as RequestClient)
    await expect(api.retry(id, 'analysis-retry-idem-001')).resolves.toEqual({ task: retried, location: `/api/v1/analysis-tasks/${retried.id}` })
    expect(requestWithMetadata).toHaveBeenCalledWith({ method: 'POST', path: `/analysis-tasks/${id}/retry`, idempotencyKey: 'analysis-retry-idem-001' })
    const wrongParent = { ...retried, retry_of: '00000000-0000-4000-8000-000000000099' }
    const invalidApi = new AnalysisApi({ requestWithMetadata: vi.fn().mockResolvedValue({ status: 202, data: wrongParent, headers: { Location: `/analysis-tasks/${retried.id}` } }) } as unknown as RequestClient)
    await expect(invalidApi.retry(id, 'analysis-retry-idem-002')).rejects.toThrow('Location')
  })

  it('uses POST for explicit cancellation and leaves the response status authoritative', async () => {
    const cancelled = { ...task, status: 'cancelled' as const }
    const request = vi.fn().mockResolvedValue(cancelled)
    const api = new AnalysisApi({ request } as unknown as RequestClient)
    await expect(api.cancel(id)).resolves.toEqual(cancelled)
    expect(request).toHaveBeenCalledWith({ method: 'POST', path: `/analysis-tasks/${id}/cancel` })
  })
})
