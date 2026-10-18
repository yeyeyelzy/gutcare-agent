import { describe, expect, it, vi } from 'vitest'
import { MedicalDocumentsApi } from '../src/api/medicalDocumentsApi'
import type { RequestClient } from '../src/api/requestClient'

describe('MedicalDocumentsApi', () => {
  it('uses generated F02 candidate DTO operations and independent decision idempotency keys', async () => {
    const request = vi.fn().mockResolvedValue({ items: [], next_cursor: null })
    const uploadThroughGateway = vi.fn().mockResolvedValue(undefined)
    const api = new MedicalDocumentsApi({ request, uploadThroughGateway } as unknown as RequestClient)
    const upload = { purpose: 'medical_document' as const, file_name: 'report.pdf', content_type: 'application/pdf' as const, size_bytes: 12 }
    await api.createUpload(upload, 'upload-key')
    expect(request).toHaveBeenLastCalledWith({ method: 'POST', path: '/files/uploads', data: upload, idempotencyKey: 'upload-key' })
    await api.upload('https://api.example.invalid/uploads/abcdefghijklmnopqrstuvwx12345678', new ArrayBuffer(12), 'application/pdf')
    expect(uploadThroughGateway).toHaveBeenCalledWith('https://api.example.invalid/uploads/abcdefghijklmnopqrstuvwx12345678', expect.any(ArrayBuffer), 'application/pdf')
    await api.completeUpload('upload-id')
    expect(request).toHaveBeenLastCalledWith({ method: 'POST', path: '/files/uploads/upload-id/complete' })
    await api.list({ limit: 20, cursor: 'opaque cursor', document_type: 'lab_report' })
    expect(request).toHaveBeenLastCalledWith({ method: 'GET', path: '/medical-documents?cursor=opaque+cursor&limit=20&document_type=lab_report' })
    const body = { file_object_id: 'file-id', document_type: 'lab_report', processing_mode: 'store_only' } as const
    await api.create(body)
    expect(request).toHaveBeenLastCalledWith({ method: 'POST', path: '/medical-documents', data: body })
    await api.get('document/id')
    expect(request).toHaveBeenLastCalledWith({ method: 'GET', path: '/medical-documents/document%2Fid' })
    await api.listCandidates('document/id')
    expect(request).toHaveBeenLastCalledWith({ method: 'GET', path: '/medical-documents/document%2Fid/candidates' })
    const decision = { decision: 'accept', record_version: 3, value: { certainty: 'suspected' } } as const
    await api.decideCandidate('candidate/id', decision, 'candidate-decision-key-1')
    expect(request).toHaveBeenLastCalledWith({ method: 'POST', path: '/medical-field-candidates/candidate%2Fid/decision', data: decision, idempotencyKey: 'candidate-decision-key-1' })
    await api.delete('document-id')
    expect(request).toHaveBeenLastCalledWith({ method: 'DELETE', path: '/medical-documents/document-id' })
    await api.createDownloadGrant('file-id')
    expect(request).toHaveBeenLastCalledWith({ method: 'POST', path: '/files/file-id/download-grants' })
    expect(request.mock.calls.filter(([options]) => options.method === 'POST' && options.path.endsWith('/decision'))).toHaveLength(1)
  })
})
