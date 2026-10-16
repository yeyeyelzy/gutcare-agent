export interface ProblemDetails {
  type: string
  title: string
  status: number
  detail?: string
  instance?: string
  code: string
  request_id: string
  errors?: Array<Record<string, unknown>>
}

export type AppErrorKind = 'http' | 'network' | 'timeout' | 'offline' | 'unavailable' | 'protocol'

export class AppError extends Error {
  readonly kind: AppErrorKind
  readonly status?: number
  readonly code?: string
  readonly requestId?: string
  readonly problem?: ProblemDetails

  constructor(kind: AppErrorKind, message: string, details: { status?: number; code?: string; requestId?: string; problem?: ProblemDetails } = {}) {
    super(message)
    this.name = 'AppError'
    this.kind = kind
    this.status = details.status
    this.code = details.code
    this.requestId = details.requestId
    this.problem = details.problem
  }
}

export function mapProblemDetails(status: number, payload: unknown): AppError {
  const problem = isProblemDetails(payload) ? payload : undefined
  const kind = status === 502 || status === 503 || status === 504 ? 'unavailable' : 'http'
  return new AppError(
    kind,
    problem?.detail ?? problem?.title ?? `请求失败（${status}）`,
    { status, code: problem?.code, requestId: problem?.request_id, problem },
  )
}

function isProblemDetails(value: unknown): value is ProblemDetails {
  if (typeof value !== 'object' || value === null || Array.isArray(value)) return false
  const candidate = value as Record<string, unknown>
  return typeof candidate.type === 'string'
    && typeof candidate.title === 'string'
    && typeof candidate.status === 'number'
    && typeof candidate.code === 'string'
    && typeof candidate.request_id === 'string'
}
