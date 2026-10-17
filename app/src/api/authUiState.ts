import { AppError } from './errors'

export interface AuthProblemPresentation { message: string; requestId?: string }

/** Auth screens use stable copy and never render untrusted server detail text. */
export function presentAuthProblem(error: unknown, fallback: string): AuthProblemPresentation | null {
  if (!error) return null
  if (error instanceof AppError) {
    const message = error.kind === 'offline' || error.kind === 'network' || error.kind === 'timeout'
      ? '网络暂不可用，请检查连接后重试。'
      : error.status === 429
        ? '操作过于频繁，请稍后重试。'
        : error.status === 401
          ? '邮箱或密码不正确，或邮箱尚未验证。'
          : error.status === 422
            ? '请检查输入信息或令牌后重试。'
            : error.kind === 'unavailable' || (error.status !== undefined && error.status >= 500)
              ? '服务暂时不可用，请稍后重试。'
              : fallback
    const requestId = error.requestId ?? error.problem?.request_id
    return { message, ...(requestId ? { requestId } : {}) }
  }
  if (typeof error === 'object' && error !== null && 'kind' in error) {
    const projected = error as { kind: string; status?: number; code?: string; requestId?: string }
    const message = projected.kind === 'offline' || projected.kind === 'network' || projected.kind === 'timeout'
      ? '网络暂不可用，请检查连接后重试。'
      : projected.kind === 'unavailable' || (projected.status !== undefined && projected.status >= 500)
        ? '服务暂时不可用，请稍后重试。'
        : fallback
    return { message, ...(projected.requestId ? { requestId: projected.requestId } : {}) }
  }
  return { message: fallback }
}

export function isGcButtonDisabled(disabled: boolean, busy: boolean): boolean {
  return disabled || busy
}
