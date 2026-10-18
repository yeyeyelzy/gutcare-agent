import type { RequestClient } from './requestClient'
import type { Advice, AdviceFeedback, AdviceFeedbackRequest, AdvicePage } from './openapiTypes'

export interface AdviceListQuery {
  limit?: number
  cursor?: string
}

/** Patient advice endpoints only; callback/agent operations are intentionally absent. */
export class AdviceApi {
  constructor(private readonly client: RequestClient) {}

  list(query: AdviceListQuery = {}): Promise<AdvicePage> {
    const params = new URLSearchParams()
    if (query.limit !== undefined) params.set('limit', String(query.limit))
    if (query.cursor) params.set('cursor', query.cursor)
    return this.client.request<AdvicePage>({
      method: 'GET', path: `/advice${params.size ? `?${params.toString()}` : ''}`,
    })
  }

  get(id: string): Promise<Advice> {
    return this.client.request<Advice>({ method: 'GET', path: `/advice/${encodeURIComponent(id)}` })
  }

  markRead(id: string): Promise<Advice> {
    return this.client.request<Advice>({ method: 'POST', path: `/advice/${encodeURIComponent(id)}/read` })
  }

  archive(id: string): Promise<Advice> {
    return this.client.request<Advice>({ method: 'POST', path: `/advice/${encodeURIComponent(id)}/archive` })
  }

  feedback(id: string, body: AdviceFeedbackRequest, idempotencyKey: string): Promise<AdviceFeedback> {
    return this.client.request<AdviceFeedback>({
      method: 'PUT', path: `/advice/${encodeURIComponent(id)}/feedback`, data: body, idempotencyKey,
    })
  }
}
