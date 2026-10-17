import type { RequestClient } from './requestClient'
import type { HealthRecord, RecordPage, RecordPatch, RecordType, RecordWrite, SymptomStatusHistory } from './openapiTypes'

export interface RecordListQuery {
  limit?: number
  cursor?: string
  since?: string
  until?: string
}

export class RecordsApi {
  constructor(private readonly client: RequestClient) {}

  list(type: RecordType, query: RecordListQuery = {}): Promise<RecordPage> {
    const params = new URLSearchParams()
    if (query.limit !== undefined) params.set('limit', String(query.limit))
    if (query.cursor) params.set('cursor', query.cursor)
    if (query.since) params.set('since', query.since)
    if (query.until) params.set('until', query.until)
    const suffix = params.size ? `?${params.toString()}` : ''
    return this.client.request<RecordPage>({ method: 'GET', path: `/${type}${suffix}` })
  }

  get(type: RecordType, id: string): Promise<HealthRecord> {
    return this.client.request<HealthRecord>({ method: 'GET', path: `/${type}/${encodeURIComponent(id)}` })
  }

  create(type: RecordType, body: RecordWrite, idempotencyKey: string): Promise<HealthRecord> {
    return this.client.request<HealthRecord>({
      method: 'POST', path: `/${type}`, data: body, idempotencyKey,
    })
  }

  update(type: RecordType, id: string, body: RecordPatch): Promise<HealthRecord> {
    return this.client.request<HealthRecord>({
      method: 'PATCH', path: `/${type}/${encodeURIComponent(id)}`, data: body,
    })
  }

  delete(type: RecordType, id: string, recordVersion: number): Promise<void> {
    const query = new URLSearchParams({ record_version: String(recordVersion) })
    return this.client.request<void>({
      method: 'DELETE', path: `/${type}/${encodeURIComponent(id)}?${query.toString()}`,
    })
  }

  symptomStatusHistory(id: string): Promise<SymptomStatusHistory> {
    return this.client.request<SymptomStatusHistory>({
      method: 'GET', path: `/symptom-records/${encodeURIComponent(id)}/status-history`,
    })
  }
}
