import { describe, expect, it, vi } from 'vitest'
import { canRetryRecordImageRequest, candidateRequiresFoodName, disclosureIsUsable, hasRecordImageConsent, mutateThenRefresh, recordImageLimit, runVisibleOperation, submitRecordImageRequest, uploadSelectedRecordImages, VisibleOperationGate } from '../src/api/recordImageBehavior'
import type { RecordImageAttachment, RecordImageCandidate } from '../src/api/openapiTypes'

const attachment = (id: string): RecordImageAttachment => ({ id, record_id: 'r', position: 0, record_version: 2, image_set_version: 2, file_status: 'available', created_at: 'now' })
const candidate = (candidate_type: string, status = 'pending'): RecordImageCandidate => ({ id: candidate_type, candidate_group_key: 'g1', candidate_type, value: 'rice', confidence_band: 'medium', status, candidate_version: 1, attachment_id: 'a', uncertainty_code: 'other' } as unknown as RecordImageCandidate)

describe('record image behavior', () => {
  it('enforces diet/stool limits and name-first grouped candidate decisions', () => {
    expect(recordImageLimit('diet')).toBe(10)
    expect(recordImageLimit('stool')).toBe(1)
    const name = candidate('food_name')
    expect(candidateRequiresFoodName(candidate('food_category'), [name])).toBe(true)
    expect(candidateRequiresFoodName(candidate('portion_description'), [name])).toBe(true)
    expect(candidateRequiresFoodName(candidate('food_category'), [candidate('food_name', 'accepted')])).toBe(false)
    expect(candidateRequiresFoodName(candidate('bristol_type'), [name])).toBe(false)
  })

  it('fails closed when consent or purpose notice is missing or disabled', () => {
    expect(hasRecordImageConsent([], 'attachment')).toBe(false)
    expect(hasRecordImageConsent([{ consent_type: 'health_data_processing', granted: true }, { consent_type: 'sensitive_image', granted: true }] as never, 'recognition')).toBe(false)
    expect(disclosureIsUsable(null)).toBe(false)
    expect(disclosureIsUsable({ enabled: false, policy_version: 'v1' } as never)).toBe(false)
  })

  it('keeps old candidate state after a successful decision POST whose GET refresh fails; no new idempotent submission', async () => {
    const old = [attachment('old')]
    const decidePost = vi.fn().mockResolvedValue(undefined)
    const getRequest = vi.fn().mockRejectedValue(new Error('offline'))
    const result = await mutateThenRefresh(old, decidePost, getRequest, () => true)
    expect(decidePost).toHaveBeenCalledTimes(1)
    expect(getRequest).toHaveBeenCalledTimes(1)
    expect(result.value).toBe(old)
    expect(result.refreshed).toBe(false)
    expect(result.refreshError).toBeInstanceOf(Error)
  })

  it('treats a failed decision POST as unsubmitted and does not fetch or repeat it', async () => {
    const decidePost = vi.fn().mockRejectedValue(new Error('rejected'))
    const getRequest = vi.fn()
    await expect(mutateThenRefresh([attachment('old')], decidePost, getRequest, () => true)).rejects.toThrow('rejected')
    expect(decidePost).toHaveBeenCalledTimes(1)
    expect(getRequest).not.toHaveBeenCalled()
  })

  it('replaces candidate state after a successful decision POST and refresh', async () => {
    const previous = [attachment('old')]
    const latest = [attachment('new')]
    const decidePost = vi.fn().mockResolvedValue(undefined)
    const getRequest = vi.fn().mockResolvedValue(latest)
    const result = await mutateThenRefresh(previous, decidePost, getRequest, () => true)
    expect(result.refreshed).toBe(true)
    expect(result.value).toBe(latest)
    expect(decidePost).toHaveBeenCalledTimes(1)
    expect(getRequest).toHaveBeenCalledTimes(1)
  })

  it('does not resubmit a failed request unless retry is explicitly eligible', () => {
    expect(canRetryRecordImageRequest({ status: 'failed' } as never, 1)).toBe(true)
    expect(canRetryRecordImageRequest({ status: 'processing' } as never, 1)).toBe(false)
    expect(canRetryRecordImageRequest({ status: 'failed' } as never, 0)).toBe(false)
  })

  it('uses retry only after explicit retry selection and an existing request id', async () => {
    const create = vi.fn().mockResolvedValue('new')
    const retry = vi.fn().mockResolvedValue('retried')
    const body = { record_version: 1, image_set_version: 1, disclosure_token: 'opaque' }
    await submitRecordImageRequest({ explicitlyRetry: false, retryRequestId: 'existing', body, create, retry })
    expect(create).toHaveBeenCalledTimes(1)
    expect(retry).not.toHaveBeenCalled()
    await submitRecordImageRequest({ explicitlyRetry: true, retryRequestId: 'existing', body, create, retry })
    expect(retry).toHaveBeenCalledTimes(1)
    await submitRecordImageRequest({ explicitlyRetry: true, body, create, retry })
    expect(create).toHaveBeenCalledTimes(2)
  })

  it('clears bytes and selected paths on upload failure and stops later work after hide', async () => {
    const gate = new VisibleOperationGate()
    const bytes = new Uint8Array([7, 8]).buffer
    const read = vi.fn().mockResolvedValue(bytes)
    const upload = vi.fn(async () => { throw new Error('gateway failure') })
    const cleanup = vi.fn()
    const states: string[] = []
    await uploadSelectedRecordImages({ selected: [
      { path: '/private/a.jpg', sizeBytes: 2, contentType: 'image/jpeg' },
      { path: '/private/b.jpg', sizeBytes: 2, contentType: 'image/jpeg' },
    ], isCurrent: () => gate.isCurrent(0), read, upload, cleanup, onState: (_index, state) => states.push(state), onAttached: vi.fn() })
    expect(states).toContain('error')
    expect(new Uint8Array(bytes)).toEqual(new Uint8Array([0, 0]))
    expect(cleanup.mock.calls.map(([path]) => path)).toEqual(['/private/a.jpg', '/private/b.jpg'])

    const gate2 = new VisibleOperationGate()
    let release!: (value: ArrayBuffer) => void
    const deferred = new Promise<ArrayBuffer>((resolve) => { release = resolve })
    const lateUpload = vi.fn()
    const cleanLate = vi.fn()
    const pending = uploadSelectedRecordImages({ selected: [{ path: '/private/late.png', sizeBytes: 1, contentType: 'image/png' }], isCurrent: () => gate2.isCurrent(0), read: () => deferred, upload: lateUpload, cleanup: cleanLate, onState: vi.fn(), onAttached: vi.fn() })
    gate2.hide()
    release(new Uint8Array([1]).buffer)
    const result = await pending
    expect(result.interrupted).toBe(true)
    expect(lateUpload).not.toHaveBeenCalled()
    expect(cleanLate).toHaveBeenCalledWith('/private/late.png')
  })

  it('stops a multi-image attach sequence on conflict without resubmitting and cleans remaining paths', async () => {
    const upload = vi.fn().mockRejectedValue(Object.assign(new Error('conflict'), { status: 409 }))
    const cleanup = vi.fn()
    const result = await uploadSelectedRecordImages({ selected: [
      { path: '/private/one.jpg', sizeBytes: 1, contentType: 'image/jpeg' },
      { path: '/private/two.jpg', sizeBytes: 1, contentType: 'image/jpeg' },
    ], isCurrent: () => true, read: async () => new Uint8Array([1]).buffer, upload, cleanup, stopOnError: (error) => (error as { status?: number }).status === 409, onState: vi.fn(), onAttached: vi.fn() })
    expect(result.stopped).toBe(true)
    expect(upload).toHaveBeenCalledTimes(1)
    expect(cleanup.mock.calls.map(([path]) => path)).toEqual(['/private/one.jpg', '/private/two.jpg'])
  })

  it('invalidates responses after hide and unmount', () => {
    const gate = new VisibleOperationGate()
    const hidden = gate.snapshot()
    gate.hide()
    expect(gate.isCurrent(hidden)).toBe(false)
    gate.show()
    const unmounted = gate.snapshot()
    gate.dispose()
    expect(gate.isCurrent(unmounted)).toBe(false)
  })

  it.each(['hide', 'unmount'] as const)('does not write success or rejection state after %s while consent/disclosure is pending', async (lifecycleEvent) => {
    for (const outcome of ['resolve', 'reject'] as const) {
      const gate = new VisibleOperationGate()
      let resolve!: (value: string) => void
      let reject!: (error: Error) => void
      const pending = new Promise<string>((res, rej) => { resolve = res; reject = rej })
      let state = 'unchanged'
      const operation = runVisibleOperation(gate, () => pending, (value) => { state = value }, () => { state = 'error' })
      if (lifecycleEvent === 'hide') gate.hide(); else gate.dispose()
      if (outcome === 'resolve') resolve('notice-open'); else reject(new Error('late rejection'))
      await operation
      expect(state).toBe('unchanged')
    }
  })
})
