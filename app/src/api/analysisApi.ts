import type { RequestClient } from './requestClient'
import type { AnalysisTask, AnalysisTaskPage, AnalysisTaskPreview, AnalysisTaskRequest } from './openapiTypes'

export interface AnalysisTaskListQuery {
  limit?: number
  cursor?: string
}

export interface AcceptedAnalysisTask {
  task: AnalysisTask
  location: string
}

/** F08 transport surface; every request/response DTO is generated from OpenAPI. */
export class AnalysisApi {
  constructor(private readonly client: RequestClient) {}

  preview(query: AnalysisTaskRequest): Promise<AnalysisTaskPreview> {
    const params = new URLSearchParams({ analysis_type: query.analysis_type })
    if (query.requested_from) params.set('requested_from', query.requested_from)
    if (query.requested_to) params.set('requested_to', query.requested_to)
    return this.client.request<AnalysisTaskPreview>({ method: 'GET', path: `/analysis-tasks/preview?${params.toString()}` })
  }

  async create(body: AnalysisTaskRequest, idempotencyKey: string): Promise<AcceptedAnalysisTask> {
    const response = await this.client.requestWithMetadata<AnalysisTask>({
      method: 'POST', path: '/analysis-tasks', data: body, idempotencyKey,
    })
    const location = response.headers?.Location ?? response.headers?.location ?? ''
    if (response.status !== 202 || !isTaskLocation(location, response.data.id)) {
      throw new Error('服务响应缺少有效的分析任务 Location。')
    }
    return { task: response.data, location }
  }

  list(query: AnalysisTaskListQuery = {}): Promise<AnalysisTaskPage> {
    const params = new URLSearchParams()
    if (query.limit !== undefined) params.set('limit', String(query.limit))
    if (query.cursor) params.set('cursor', query.cursor)
    return this.client.request<AnalysisTaskPage>({
      method: 'GET', path: `/analysis-tasks${params.size ? `?${params.toString()}` : ''}`,
    })
  }

  get(id: string): Promise<AnalysisTask> {
    return this.client.request<AnalysisTask>({ method: 'GET', path: `/analysis-tasks/${encodeURIComponent(id)}` })
  }

  cancel(id: string): Promise<AnalysisTask> {
    return this.client.request<AnalysisTask>({ method: 'POST', path: `/analysis-tasks/${encodeURIComponent(id)}/cancel` })
  }

  async retry(id: string, idempotencyKey: string): Promise<AcceptedAnalysisTask> {
    const response = await this.client.requestWithMetadata<AnalysisTask>({
      method: 'POST', path: `/analysis-tasks/${encodeURIComponent(id)}/retry`, idempotencyKey,
    })
    const location = response.headers?.Location ?? response.headers?.location ?? ''
    if (response.status !== 202 || !isTaskLocation(location, response.data.id)) {
      throw new Error('服务响应缺少有效的分析任务 Location。')
    }
    return { task: response.data, location }
  }
}

function isTaskLocation(value: string, taskId: string): boolean {
  return value === `/api/v1/analysis-tasks/${taskId}` || value === `/analysis-tasks/${taskId}`
}
