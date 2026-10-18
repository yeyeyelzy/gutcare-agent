import type { RequestClient } from './requestClient'
import type { MedicalFactConflict, MedicalFactConflictResolution, MedicalFactConflictResolutionRequest } from './openapiTypes'

export type MedicalFactConflictStatusFilter = 'open' | 'resolved' | 'invalidated' | 'all'

/** Patient-only conflict review operations. Results preserve the service's order. */
export class MedicalFactConflictsApi {
  constructor(private readonly client: RequestClient) {}

  list(status: MedicalFactConflictStatusFilter = 'open'): Promise<MedicalFactConflict[]> {
    return this.client.request({ method: 'GET', path: `/medical-fact-conflicts?status=${encodeURIComponent(status)}` })
  }

  get(conflictId: string): Promise<MedicalFactConflict> {
    return this.client.request({ method: 'GET', path: `/medical-fact-conflicts/${encodeURIComponent(conflictId)}` })
  }

  keepBoth(conflictId: string, body: MedicalFactConflictResolutionRequest, idempotencyKey: string): Promise<MedicalFactConflictResolution> {
    return this.client.request({ method: 'POST', path: `/medical-fact-conflicts/${encodeURIComponent(conflictId)}/resolve`, data: body, idempotencyKey })
  }
}
