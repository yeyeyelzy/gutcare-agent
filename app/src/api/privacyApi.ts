import type { PrivacyDeletionAccepted, PrivacyDeletionStatus, PrivacyDeletionStatusRequest } from './openapiTypes'
import type { RequestClient } from './requestClient'

export class PrivacyApi {
  constructor(private readonly client: RequestClient) {}

  requestAccountDeletion(): Promise<PrivacyDeletionAccepted> {
    return this.client.request({ method: 'POST', path: '/patients/me/account-deletion' })
  }

  getDeletionStatus(operationId: string, body: PrivacyDeletionStatusRequest): Promise<PrivacyDeletionStatus> {
    return this.client.request({
      method: 'POST',
      path: `/privacy/deletion-operations/${encodeURIComponent(operationId)}/status`,
      data: body,
      retryOnUnauthorized: false,
    })
  }
}
