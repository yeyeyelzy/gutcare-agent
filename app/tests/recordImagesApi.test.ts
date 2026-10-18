import { describe, expect, it, vi } from 'vitest'
import { RecordImagesApi } from '../src/api/recordImagesApi'
import type { RequestClient } from '../src/api/requestClient'

describe('RecordImagesApi', () => {
  it('uploads through the same-origin gateway, completes scanning, then attaches with both versions', async () => {
    const order: string[] = []
    const request = vi.fn(async (options: { method: string; path: string; data?: unknown }) => {
      order.push(`${options.method} ${options.path}`)
      if (options.path === '/files/uploads') return { upload_id: 'upload-id', upload_url: 'https://api.test/uploads/abcdefghijklmnopqrstuvwx12345678', expires_at: '2026-10-18T10:00:00Z' }
      if (options.path.endsWith('/complete')) return { id: 'file-id', storage_status: 'available', content_type: 'image/jpeg', size_bytes: 12 }
      return { id: 'attachment-id', record_id: 'record-id', position: 0, record_version: 8, image_set_version: 3, file_status: 'available', created_at: '2026-10-18T09:00:00Z' }
    })
    const uploadThroughGateway = vi.fn(async () => { order.push('PUT gateway') })
    const api = new RecordImagesApi({ request, uploadThroughGateway } as unknown as RequestClient)
    const bytes = new Uint8Array([1, 2, 3]).buffer
    const result = await api.uploadAndAttach({ kind: 'diet', recordId: 'record-id', recordVersion: 7, imageSetVersion: 2, position: 0, name: 'record-image.jpg', contentType: 'image/jpeg', bytes })
    expect(order).toEqual([
      'POST /files/uploads', 'PUT gateway', 'POST /files/uploads/upload-id/complete',
      'POST /dietary-records/record-id/images',
    ])
    expect(request.mock.calls[0]?.[0].data).toMatchObject({ purpose: 'diet_image', content_type: 'image/jpeg', size_bytes: 3 })
    expect(request.mock.calls[2]?.[0].data).toMatchObject({ file_object_id: 'file-id', record_version: 7, image_set_version: 2, position: 0 })
    expect(result?.id).toBe('attachment-id')
  })

  it('uses explicit purpose disclosure, retry, candidate decisions and versioned image deletion endpoints', async () => {
    const request = vi.fn().mockResolvedValue({})
    const api = new RecordImagesApi({ request } as unknown as RequestClient)
    await api.disclosure('stool_image_recognition')
    expect(request).toHaveBeenLastCalledWith({ method: 'GET', path: '/record-image-recognition-disclosures?purpose=stool_image_recognition' })
    await api.remove('image-id', 4, 2)
    expect(request).toHaveBeenLastCalledWith({ method: 'DELETE', path: '/record-images/image-id?record_version=4&image_set_version=2' })
    await api.retry('request-id', { record_version: 4, image_set_version: 2, disclosure_token: 'opaque' })
    expect(request.mock.calls.at(-1)?.[0]).toMatchObject({ method: 'POST', path: '/record-image-recognition-requests/request-id/retry' })
    await api.decide('candidate-id', { candidate_version: 1, record_version: 4, image_set_version: 2, action: 'reject' })
    expect(request.mock.calls.at(-1)?.[0]).toMatchObject({ method: 'POST', path: '/record-image-candidates/candidate-id/decision' })
  })

  it.each(['session', 'gateway', 'complete', 'attach'] as const)('stops the upload chain when %s fails', async (failedStage) => {
    const calls: string[] = []
    const request = vi.fn(async (options: { method: string; path: string }) => {
      calls.push(options.path)
      if (failedStage === 'session' && options.path === '/files/uploads') throw new Error('session failed')
      if (failedStage === 'complete' && options.path.endsWith('/complete')) throw new Error('complete failed')
      if (failedStage === 'attach' && options.path.endsWith('/images')) throw new Error('attach failed')
      if (options.path === '/files/uploads') return { upload_id: 'u', upload_url: 'https://api.test/gateway' }
      if (options.path.endsWith('/complete')) return { id: 'f', storage_status: 'available' }
      return { id: 'a' }
    })
    const uploadThroughGateway = vi.fn(async () => { calls.push('gateway'); if (failedStage === 'gateway') throw new Error('gateway failed') })
    const api = new RecordImagesApi({ request, uploadThroughGateway } as unknown as RequestClient)
    await expect(api.uploadAndAttach({ kind: 'diet', recordId: 'r', recordVersion: 1, imageSetVersion: 1, position: 0, name: 'record-image.jpg', contentType: 'image/jpeg', bytes: new Uint8Array([1]).buffer })).rejects.toThrow()
    if (failedStage === 'session') expect(calls).toEqual(['/files/uploads'])
    if (failedStage === 'gateway') expect(calls).toEqual(['/files/uploads', 'gateway'])
    if (failedStage === 'complete') expect(calls).toEqual(['/files/uploads', 'gateway', '/files/uploads/u/complete'])
    if (failedStage === 'attach') expect(calls).toEqual(['/files/uploads', 'gateway', '/files/uploads/u/complete', '/dietary-records/r/images'])
  })

  it('does not continue to complete or attach when the view becomes inactive during gateway upload', async () => {
    let active = true
    const request = vi.fn(async (options: { path: string }) => {
      if (options.path === '/files/uploads') return { upload_id: 'u', upload_url: 'https://api.test/gateway' }
      return { id: 'a', storage_status: 'available' }
    })
    const uploadThroughGateway = vi.fn(async () => { active = false })
    const api = new RecordImagesApi({ request, uploadThroughGateway } as unknown as RequestClient)
    const result = await api.uploadAndAttach({ kind: 'diet', recordId: 'r', recordVersion: 1, imageSetVersion: 1, position: 0, name: 'record-image.jpg', contentType: 'image/jpeg', bytes: new Uint8Array([1]).buffer, isActive: () => active })
    expect(result).toBeNull()
    expect(request).toHaveBeenCalledTimes(1)
  })
})
