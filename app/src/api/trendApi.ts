import type { RequestClient } from './requestClient'
import type { TrendBucket, TrendResponse } from './openapiTypes'

export interface TrendQuery {
  from: string
  to: string
  bucket: TrendBucket
}

export class TrendApi {
  constructor(private readonly client: RequestClient) {}

  get(query: TrendQuery): Promise<TrendResponse> {
    const params = new URLSearchParams({ from: query.from, to: query.to, bucket: query.bucket })
    return this.client.request<TrendResponse>({ method: 'GET', path: `/trends?${params.toString()}` })
  }
}
