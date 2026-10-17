import type { RequestClient } from './requestClient'
import type { RiskAlert, RiskAlertPage } from './openapiTypes'

export interface RiskAlertListQuery {
  limit?: number
  cursor?: string
  unread_only?: boolean
}

export class RiskApi {
  constructor(private readonly client: RequestClient) {}

  list(query: RiskAlertListQuery = {}): Promise<RiskAlertPage> {
    const params = new URLSearchParams()
    if (query.limit !== undefined) params.set('limit', String(query.limit))
    if (query.cursor) params.set('cursor', query.cursor)
    if (query.unread_only !== undefined) params.set('unread_only', String(query.unread_only))
    const suffix = params.size ? `?${params.toString()}` : ''
    return this.client.request({ method: 'GET', path: `/risk-alerts${suffix}` })
  }

  get(id: string): Promise<RiskAlert> {
    return this.client.request({ method: 'GET', path: `/risk-alerts/${encodeURIComponent(id)}` })
  }

  markRead(id: string): Promise<RiskAlert> {
    return this.client.request({ method: 'POST', path: `/risk-alerts/${encodeURIComponent(id)}/read` })
  }

  reevaluate(id: string): Promise<RiskAlert> {
    return this.client.request({ method: 'POST', path: `/risk-alerts/${encodeURIComponent(id)}/reevaluate` })
  }
}
