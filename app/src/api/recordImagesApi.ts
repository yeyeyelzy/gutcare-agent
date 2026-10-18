import type { RequestClient } from './requestClient'
import type {
  RecordImageAttachment, RecordImageCandidateDecision, RecordImageDisclosure,
  RecordImageDisclosureAcknowledgment, RecordImageDisclosureToken,
  RecordImagePurpose, RecordImageRecognitionCreate, RecordImageRecognitionRequest,
  UploadRequest, UploadSession, UploadedFileObject,
} from './openapiTypes'

export type RecordImageKind = 'diet' | 'stool'

/** F03/F04 image attachments and recognition, using only the authenticated same-origin file gateway. */
export class RecordImagesApi {
  constructor(private readonly client: RequestClient) {}

  async uploadAndAttach(input: {
    kind: RecordImageKind; recordId: string; recordVersion: number; imageSetVersion: number;
    position: number; name: string; contentType: 'image/jpeg' | 'image/png'; bytes: ArrayBuffer;
    onScanning?: () => void;
    isActive?: () => boolean;
  }): Promise<RecordImageAttachment | null> {
    const active = input.isActive ?? (() => true)
    if (!active()) return null
    const uploadRequest: UploadRequest = {
      purpose: input.kind === 'diet' ? 'diet_image' : 'stool_image',
      file_name: input.name,
      content_type: input.contentType,
      size_bytes: input.bytes.byteLength,
    }
    const session = await this.client.request<UploadSession>({
      method: 'POST', path: '/files/uploads', data: uploadRequest, idempotencyKey: uuid(),
    })
    if (!active()) return null
    await this.client.uploadThroughGateway(session.upload_url, input.bytes, input.contentType)
    if (!active()) return null
    if (active()) input.onScanning?.()
    if (!active()) return null
    const file = await this.client.request<UploadedFileObject>({
      method: 'POST', path: `/files/uploads/${encodeURIComponent(session.upload_id)}/complete`,
    })
    if (!active()) return null
    if (file.storage_status !== 'available') throw new Error('图片安全检查尚未完成。')
    const body = {
      file_object_id: file.id, record_version: input.recordVersion,
      image_set_version: input.imageSetVersion, position: input.position,
    }
    if (!active()) return null
    return this.client.request<RecordImageAttachment>({
      method: 'POST',
      path: `/${input.kind === 'diet' ? 'dietary' : 'stool'}-records/${encodeURIComponent(input.recordId)}/images`,
      data: body, idempotencyKey: uuid(),
    })
  }

  list(kind: RecordImageKind, recordId: string): Promise<RecordImageAttachment[]> {
    return this.client.request({ method: 'GET', path: `/${kind === 'diet' ? 'dietary' : 'stool'}-records/${encodeURIComponent(recordId)}/images` })
  }

  remove(imageId: string, recordVersion: number, imageSetVersion: number): Promise<void> {
    const query = new URLSearchParams({ record_version: String(recordVersion), image_set_version: String(imageSetVersion) })
    return this.client.request({ method: 'DELETE', path: `/record-images/${encodeURIComponent(imageId)}?${query}` })
  }

  disclosure(purpose: RecordImagePurpose): Promise<RecordImageDisclosure> {
    return this.client.request({ method: 'GET', path: `/record-image-recognition-disclosures?${new URLSearchParams({ purpose })}` })
  }

  acknowledge(body: RecordImageDisclosureAcknowledgment): Promise<RecordImageDisclosureToken> {
    return this.client.request({ method: 'POST', path: '/record-image-recognition-disclosures', data: body, idempotencyKey: uuid() })
  }

  create(kind: RecordImageKind, recordId: string, body: RecordImageRecognitionCreate): Promise<RecordImageRecognitionRequest> {
    return this.client.request({
      method: 'POST', path: `/${kind === 'diet' ? 'dietary' : 'stool'}-records/${encodeURIComponent(recordId)}/image-recognition-requests`,
      data: body, idempotencyKey: uuid(),
    })
  }

  getRequest(requestId: string): Promise<RecordImageRecognitionRequest> {
    return this.client.request({ method: 'GET', path: `/record-image-recognition-requests/${encodeURIComponent(requestId)}` })
  }

  retry(requestId: string, body: RecordImageRecognitionCreate): Promise<RecordImageRecognitionRequest> {
    return this.client.request({ method: 'POST', path: `/record-image-recognition-requests/${encodeURIComponent(requestId)}/retry`, data: body, idempotencyKey: uuid() })
  }

  decide(candidateId: string, body: RecordImageCandidateDecision): Promise<void> {
    return this.client.request({ method: 'POST', path: `/record-image-candidates/${encodeURIComponent(candidateId)}/decision`, data: body, idempotencyKey: uuid() })
  }
}

function uuid(): string {
  if (typeof crypto !== 'undefined' && 'randomUUID' in crypto) return crypto.randomUUID()
  return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, (digit) => {
    const random = Math.floor(Math.random() * 16)
    return digit === 'x' ? random.toString(16) : ((random & 0x3) | 0x8).toString(16)
  })
}
