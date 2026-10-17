import type { RequestClient } from './requestClient'
import type { MoodDetail, MoodPage, MoodPatch, MoodWrite } from './openapiTypes'

export interface MoodListQuery {
  limit?: number
  cursor?: string
  since?: string
  until?: string
}

export class MoodApi {
  constructor(private readonly client: RequestClient) {}

  list(query: MoodListQuery = {}): Promise<MoodPage> {
    const params = new URLSearchParams()
    if (query.limit !== undefined) params.set('limit', String(query.limit))
    if (query.cursor) params.set('cursor', query.cursor)
    if (query.since) params.set('since', query.since)
    if (query.until) params.set('until', query.until)
    const suffix = params.size ? `?${params.toString()}` : ''
    return this.client.request<MoodPage>({ method: 'GET', path: `/mood-records${suffix}` })
  }

  get(id: string): Promise<MoodDetail> {
    return this.client.request<MoodDetail>({ method: 'GET', path: `/mood-records/${encodeURIComponent(id)}` })
  }

  create(body: MoodWrite, idempotencyKey: string): Promise<MoodDetail> {
    return this.client.request<MoodDetail>({ method: 'POST', path: '/mood-records', data: body, idempotencyKey })
  }

  update(id: string, body: MoodPatch): Promise<MoodDetail> {
    return this.client.request<MoodDetail>({ method: 'PATCH', path: `/mood-records/${encodeURIComponent(id)}`, data: body })
  }

  delete(id: string, recordVersion: number): Promise<void> {
    return this.client.request<void>({
      method: 'DELETE', path: `/mood-records/${encodeURIComponent(id)}`,
      data: { record_version: recordVersion },
    })
  }
}
