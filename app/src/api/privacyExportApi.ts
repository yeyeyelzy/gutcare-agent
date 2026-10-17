import type { PrivacyExportCategory, PrivacyExportDetail, PrivacyExportPreview, PrivacyExportRequest, PrivacyExportStatus, PrivacyExportSummary } from './openapiTypes'
import type { RequestClient } from './requestClient'

export const PRIVACY_EXPORT_CATEGORIES: readonly PrivacyExportCategory[] = [
  'profile', 'consents', 'medical_documents', 'files', 'diet', 'stool', 'symptoms', 'mood',
  'medication', 'activity', 'analysis', 'advice', 'alerts', 'notifications',
]
export const PRIVACY_EXPORT_STATUSES: readonly PrivacyExportStatus[] = ['preview', 'pending', 'processing', 'ready', 'failed', 'cancelled', 'expired']

export function canConfirmPrivacyExport(status: PrivacyExportStatus): boolean { return status === 'preview' }
export function canCancelPrivacyExport(status: PrivacyExportStatus): boolean { return status === 'preview' || status === 'pending' || status === 'processing' }

export class PrivacyExportApi {
  constructor(private readonly client: RequestClient) {}

  createPreview(categories: PrivacyExportCategory[]): Promise<PrivacyExportPreview> {
    if (!categories.length || categories.some((category) => !PRIVACY_EXPORT_CATEGORIES.includes(category))) {
      return Promise.reject(new Error('请选择至少一项有效的数据类别。'))
    }
    return this.client.request({ method: 'POST', path: '/privacy/exports', data: { categories: [...new Set(categories)] } satisfies PrivacyExportRequest })
  }

  list(): Promise<PrivacyExportSummary[]> {
    return this.client.request({ method: 'GET', path: '/privacy/exports' })
  }

  get(exportId: string): Promise<PrivacyExportDetail> {
    return this.client.request({ method: 'GET', path: `/privacy/exports/${encodeURIComponent(exportId)}` })
  }

  confirm(exportId: string): Promise<void> {
    return this.client.request({ method: 'POST', path: `/privacy/exports/${encodeURIComponent(exportId)}` })
  }

  cancel(exportId: string): Promise<void> {
    return this.client.request({ method: 'POST', path: `/privacy/exports/${encodeURIComponent(exportId)}/cancel` })
  }
}
