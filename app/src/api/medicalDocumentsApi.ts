import type { RequestClient } from './requestClient'
import type { DownloadGrant, MedicalCandidateDecision, MedicalDocument, MedicalDocumentCreate, MedicalDocumentPage, MedicalFieldCandidate, UploadRequest, UploadSession, UploadedFileObject } from './openapiTypes'

export interface MedicalDocumentListQuery { cursor?: string; limit?: number; document_type?: MedicalDocument['document_type'] }

/** F02 patient-facing file/document operations, all through the business API and same-origin gateway. */
export class MedicalDocumentsApi {
  constructor(private readonly client: RequestClient) {}

  createUpload(body: UploadRequest, idempotencyKey: string): Promise<UploadSession> {
    return this.client.request({ method: 'POST', path: '/files/uploads', data: body, idempotencyKey })
  }

  upload(uploadUrl: string, bytes: ArrayBuffer, contentType: string): Promise<void> {
    return this.client.uploadThroughGateway(uploadUrl, bytes, contentType)
  }

  completeUpload(uploadId: string): Promise<UploadedFileObject> {
    return this.client.request({ method: 'POST', path: `/files/uploads/${encodeURIComponent(uploadId)}/complete` })
  }

  list(query: MedicalDocumentListQuery = {}): Promise<MedicalDocumentPage> {
    const params = new URLSearchParams()
    if (query.cursor) params.set('cursor', query.cursor)
    if (query.limit !== undefined) params.set('limit', String(query.limit))
    if (query.document_type) params.set('document_type', query.document_type)
    return this.client.request({ method: 'GET', path: `/medical-documents${params.size ? `?${params}` : ''}` })
  }

  get(documentId: string): Promise<MedicalDocument> {
    return this.client.request({ method: 'GET', path: `/medical-documents/${encodeURIComponent(documentId)}` })
  }

  listCandidates(documentId: string): Promise<MedicalFieldCandidate[]> {
    return this.client.request({ method: 'GET', path: `/medical-documents/${encodeURIComponent(documentId)}/candidates` })
  }

  decideCandidate(candidateId: string, body: MedicalCandidateDecision, idempotencyKey: string): Promise<void> {
    return this.client.request({ method: 'POST', path: `/medical-field-candidates/${encodeURIComponent(candidateId)}/decision`, data: body, idempotencyKey })
  }

  create(body: MedicalDocumentCreate): Promise<MedicalDocument> {
    return this.client.request({ method: 'POST', path: '/medical-documents', data: body })
  }

  delete(documentId: string): Promise<void> {
    return this.client.request({ method: 'DELETE', path: `/medical-documents/${encodeURIComponent(documentId)}` })
  }

  createDownloadGrant(fileId: string): Promise<DownloadGrant> {
    return this.client.request({ method: 'POST', path: `/files/${encodeURIComponent(fileId)}/download-grants` })
  }
}
