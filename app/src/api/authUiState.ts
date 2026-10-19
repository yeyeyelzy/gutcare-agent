import { AppError } from './errors'

export interface AuthProblemPresentation { message: string; requestId?: string }

/** Auth screens use stable copy and never render untrusted server detail text. */
export function presentAuthProblem(error: unknown, fallback: string): AuthProblemPresentation | null {
  if (!error) return null
  if (error instanceof AppError) {
    const secureStorageMessage = presentSecureStorageError(error.code)
    if (secureStorageMessage) return { message: secureStorageMessage }
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
  if (typeof error === 'object' && error !== null && 'code' in error) {
    const message = presentSecureStorageError(String((error as { code: unknown }).code))
    if (message) return { message }
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

function presentSecureStorageError(code: string | undefined): string | null {
  switch (code) {
    case 'DEVICE_LOCKED': return '设备当前处于锁定状态，解锁后再登录。'
    case 'KEY_INVALIDATED': return '本机安全存储密钥已失效，请重新登录；若持续发生，请联系支持并提供错误代码 KEY_INVALIDATED。'
    case 'CORRUPT_DATA': return '本机安全存储数据无效，请重新登录；若持续发生，请联系支持并提供错误代码 CORRUPT_DATA。'
    case 'UNSUPPORTED_PLATFORM': return '当前运行环境不支持安全令牌存储，请在 Android 或 iOS APP 中登录。'
    case 'INVALID_VALUE': return '登录凭据无法安全保存，请重试；若持续发生，请联系支持并提供错误代码 INVALID_VALUE。'
    case 'SECURE_STORAGE_FAILED': return '本机安全存储暂不可用，请重试；若持续发生，请联系支持并提供错误代码 SECURE_STORAGE_FAILED。'
    default: return null
  }
}

export function isGcButtonDisabled(disabled: boolean, busy: boolean): boolean {
  return disabled || busy
}
