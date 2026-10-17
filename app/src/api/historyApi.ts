import type { RequestClient } from './requestClient'
import type { HistoryCategory, HistoryPage } from './openapiTypes'

export interface HistoryTimelineQuery {
  limit?: number
  cursor?: string
  category?: readonly HistoryCategory[]
  since?: string
  until?: string
}

/** F11 timeline data is limited to the generated type/time/target contract. */
export class HistoryApi {
  constructor(private readonly client: RequestClient) {}

  list(query: HistoryTimelineQuery = {}): Promise<HistoryPage> {
    const params = new URLSearchParams()
    if (query.limit !== undefined) params.set('limit', String(query.limit))
    if (query.cursor) params.set('cursor', query.cursor)
    for (const category of [...new Set(query.category ?? [])].sort()) params.append('category', category)
    if (query.since) params.set('since', query.since)
    if (query.until) params.set('until', query.until)
    return this.client.request<HistoryPage>({
      method: 'GET',
      path: `/history/timeline${params.size ? `?${params.toString()}` : ''}`,
    })
  }
}
