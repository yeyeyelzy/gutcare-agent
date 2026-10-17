import { AppError, mapProblemDetails } from './errors'
import { RefreshCoordinator } from './refreshCoordinator'
import { isDeviceLockedError, mapSecureTokenStoreError, SecureTokenStoreError } from './secureTokenStore'
import type { SecureTokenStore } from './secureTokenStore'
import type { TokenPair } from './openapiTypes'

export type HttpMethod = 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE'
export interface RequestOptions {
  method: HttpMethod
  path: string
  data?: unknown
  headers?: Record<string, string>
  idempotencyKey?: string
  retryOnUnauthorized?: boolean
}
export interface HttpResponse<T = unknown> { status: number; data: T; headers?: Record<string, string> }
export interface HttpTransport { send<T>(url: string, options: RequestOptions & { headers: Record<string, string> }): Promise<HttpResponse<T>> }
export type SessionTokens = TokenPair
export interface RequestClientConfig {
  baseUrl: string
  appVersion: string
  transport: HttpTransport
  tokenStore: SecureTokenStore
  getAccessToken: () => string | null
  setTokens: (tokens: SessionTokens) => void
  clearSession: () => Promise<void>
  onAuthenticationRequired: () => void
  createRequestId?: () => string
}

export class RequestClient {
  private readonly refreshCoordinator = new RefreshCoordinator<SessionTokens>()

  constructor(private readonly config: RequestClientConfig) {
    if (!/^https:\/\//.test(config.baseUrl)) throw new Error('API Base URL 必须使用 HTTPS。')
  }

  async request<T>(options: RequestOptions): Promise<T> {
    const tokenUsed = this.config.getAccessToken()
    const initial = await this.send<T>(options)
    if (initial.status !== 401 || options.retryOnUnauthorized === false || options.path === '/auth/refresh') {
      return this.unwrap<T>(initial)
    }

    const currentToken = this.config.getAccessToken()
    if (currentToken === tokenUsed) {
      try {
        const tokens = await this.refreshCoordinator.run(async () => {
          try {
            return await this.refreshSession()
          } catch (error) {
            if (isDeviceLockedError(error)) {
              await this.config.clearSession()
              throw new AppError('unavailable', '设备锁定期间无法恢复会话，请解锁后重试。', { code: 'DEVICE_LOCKED' })
            }
            if (isTransientSessionError(error)) {
              await this.config.clearSession()
              throw error
            }
            await this.clearSession()
            this.config.onAuthenticationRequired()
            throw error instanceof AppError ? error : mapSecureTokenStoreError(error)
          }
        })
        this.config.setTokens(tokens)
      } catch (error) {
        if (error instanceof AppError) throw error
        if (error instanceof SecureTokenStoreError) {
          throw new AppError('unavailable', '安全会话无法继续，请重新登录。', { code: error.code })
        }
        throw new AppError('http', '登录状态已失效，请重新登录。', { status: 401 })
      }
    }
    if (!isSafeToRetry(options)) throw mapProblemDetails(initial.status, initial.data)
    const retried = await this.send<T>(options)
    if (retried.status === 401) {
      await this.clearSession()
      this.config.onAuthenticationRequired()
      throw mapProblemDetails(retried.status, retried.data)
    }
    return this.unwrap<T>(retried)
  }

  /** Rotate a saved refresh token during cold start without exposing it to UI state. */
  async restoreSession(): Promise<SessionTokens | null> {
    const refreshToken = await this.config.tokenStore.get()
    if (!refreshToken) return null
    const response = await this.send<SessionTokens>({
      method: 'POST', path: '/auth/refresh', retryOnUnauthorized: false,
      data: { refresh_token: refreshToken },
    }, false)
    const tokens = this.unwrap<SessionTokens>(response)
    await this.config.tokenStore.set(tokens.refresh_token)
    return tokens
  }

  /** Persist refresh credentials before publishing the short-lived access token in memory. */
  async acceptSession(tokens: SessionTokens): Promise<void> {
    try {
      await this.config.tokenStore.set(tokens.refresh_token)
    } catch (error) {
      if (isDeviceLockedError(error)) await this.config.clearSession()
      else await this.clearSession()
      throw mapSecureTokenStoreError(error)
    }
    this.config.setTokens(tokens)
  }

  async clearStoredSession(): Promise<void> {
    await this.clearSession()
  }

  private async refreshSession(): Promise<SessionTokens> {
    const refreshToken = await this.config.tokenStore.get()
    if (!refreshToken) throw new AppError('http', '当前会话需要重新登录。', { status: 401 })
    const response = await this.send<SessionTokens>({
      method: 'POST', path: '/auth/refresh', retryOnUnauthorized: false,
      data: { refresh_token: refreshToken },
    }, false)
    const tokens = this.unwrap<SessionTokens>(response)
    await this.config.tokenStore.set(tokens.refresh_token)
    return tokens
  }

  private async clearSession(): Promise<void> {
    await this.config.tokenStore.remove().catch(() => undefined)
    await this.config.clearSession()
  }

  private async send<T>(options: RequestOptions, includeAccessToken = true): Promise<HttpResponse<T>> {
    const headers: Record<string, string> = {
      ...Object.fromEntries(Object.entries(options.headers ?? {}).filter(([name]) =>
        !['accept', 'authorization', 'x-request-id', 'x-app-version'].includes(name.toLowerCase()),
      )),
      Accept: 'application/json, application/problem+json',
      'X-Request-ID': (this.config.createRequestId ?? createRequestId)(),
      'X-App-Version': this.config.appVersion,
    }
    if (options.data !== undefined) headers['Content-Type'] = 'application/json'
    if (options.idempotencyKey) headers['Idempotency-Key'] = options.idempotencyKey
    const token = includeAccessToken ? this.config.getAccessToken() : null
    if (token) headers.Authorization = `Bearer ${token}`
    try {
      return await this.config.transport.send<T>(`${this.config.baseUrl.replace(/\/$/, '')}${options.path}`, { ...options, headers })
    } catch (error) {
      const message = error instanceof Error ? error.message : ''
      const kind = /timeout/i.test(message) ? 'timeout' : /offline/i.test(message) ? 'offline' : 'network'
      throw new AppError(kind, kind === 'timeout' ? '请求超时，请稍后重试。' : '网络连接暂不可用。')
    }
  }

  private unwrap<T>(response: HttpResponse<T>): T {
    if (response.status >= 200 && response.status < 300) return response.data
    throw mapProblemDetails(response.status, response.data)
  }
}

function isSafeToRetry(options: RequestOptions): boolean {
  return options.method === 'GET' || options.method === 'PUT' || Boolean(options.idempotencyKey)
}

function isTransientSessionError(error: unknown): error is AppError {
  return error instanceof AppError
    && (error.kind === 'network' || error.kind === 'timeout' || error.kind === 'offline' || error.kind === 'unavailable')
}

function createRequestId(): string {
  if (typeof crypto !== 'undefined' && 'randomUUID' in crypto) return crypto.randomUUID()
  return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, (digit) => {
    const random = Math.floor(Math.random() * 16)
    return (digit === 'x' ? random : (random & 0x3) | 0x8).toString(16)
  })
}
