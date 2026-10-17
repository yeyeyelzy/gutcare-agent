import type { RequestClient } from './requestClient'
import type { ActivityPage, ActivityPatch, ActivityRecord, ActivityWrite } from './openapiTypes'

export interface ActivityListQuery {
  limit?: number
  cursor?: string
  since?: string
  until?: string
}

/** F07 endpoints generated from the frozen OpenAPI Activity schemas. */
export class ActivityApi {
  constructor(private readonly client: RequestClient) {}

  list(query: ActivityListQuery = {}): Promise<ActivityPage> {
    const params = new URLSearchParams()
    if (query.limit !== undefined) params.set('limit', String(query.limit))
    if (query.cursor) params.set('cursor', query.cursor)
    if (query.since) params.set('since', query.since)
    if (query.until) params.set('until', query.until)
    const suffix = params.size ? `?${params.toString()}` : ''
    return this.client.request<ActivityPage>({ method: 'GET', path: `/activity-records${suffix}` })
  }

  get(id: string): Promise<ActivityRecord> {
    return this.client.request<ActivityRecord>({ method: 'GET', path: `/activity-records/${encodeURIComponent(id)}` })
  }

  create(body: ActivityWrite): Promise<ActivityRecord> {
    // Frozen F07 contract does not define Idempotency-Key. UI single-flight prevents
    // duplicate taps without inventing server-side header semantics.
    return this.client.request<ActivityRecord>({ method: 'POST', path: '/activity-records', data: body })
  }

  update(id: string, body: ActivityPatch): Promise<ActivityRecord> {
    return this.client.request<ActivityRecord>({ method: 'PATCH', path: `/activity-records/${encodeURIComponent(id)}`, data: body })
  }

  delete(id: string, recordVersion: number): Promise<void> {
    return this.client.request<void>({
      method: 'DELETE', path: `/activity-records/${encodeURIComponent(id)}`,
      data: { record_version: recordVersion },
    })
  }
}
