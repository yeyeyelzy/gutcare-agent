import type { RequestClient, SessionTokens } from './requestClient'
import { isDeviceLockedError, mapSecureTokenStoreError } from './secureTokenStore'
import type { SecureTokenStore } from './secureTokenStore'
import type { LoginRequest } from './openapiTypes'
import type { useAuthStore } from '@/stores/auth'

type AuthStore = ReturnType<typeof useAuthStore>

export type { LoginRequest } from './openapiTypes'

/** Session orchestration; credentials and refresh tokens never enter persistent UI state. */
export class SessionService {
  constructor(
    private readonly client: RequestClient,
    private readonly tokenStore: SecureTokenStore,
    private readonly auth: AuthStore,
    private readonly onAuthenticationRequired: () => void,
    private readonly onLogoutCompleted: () => void = onAuthenticationRequired,
  ) {}

  async login(credentials: LoginRequest): Promise<void> {
    const tokens = await this.client.request<SessionTokens>({ method: 'POST', path: '/auth/login', data: credentials, retryOnUnauthorized: false })
    await this.client.acceptSession(tokens)
  }

  async restore(): Promise<boolean> {
    this.auth.beginRestore()
    try {
      const tokens = await this.client.restoreSession()
      if (!tokens) {
        this.auth.clear()
        return false
      }
      this.auth.acceptAccessToken(tokens.access_token)
      return true
    } catch (error) {
      if (isDeviceLockedError(error)) {
        this.auth.clear()
        throw mapSecureTokenStoreError(error)
      }
      if (isTransientRestoreError(error)) {
        this.auth.clear()
        throw error
      }
      await this.tokenStore.remove().catch(() => undefined)
      this.auth.clear()
      this.onAuthenticationRequired()
      return false
    }
  }

  async logout(): Promise<void> {
    let storageError: unknown
    try {
      await this.tokenStore.remove()
    } catch (error) {
      storageError = error
    }

    let requestError: unknown
    try {
      await this.client.request<void>({ method: 'POST', path: '/auth/logout', retryOnUnauthorized: false })
    } catch (error) {
      requestError = error
    } finally {
      this.auth.clear()
      this.onLogoutCompleted()
    }

    if (storageError !== undefined) throw mapSecureTokenStoreError(storageError)
    if (requestError !== undefined) throw requestError
  }
}

function isTransientRestoreError(error: unknown): boolean {
  return error instanceof Error && (
    ('kind' in error && ['network', 'timeout', 'offline', 'unavailable'].includes(String((error as { kind: unknown }).kind)))
    || ('status' in error && typeof (error as { status?: unknown }).status === 'number' && (error as { status: number }).status >= 500)
  )
}
