import type { RequestClient, SessionTokens } from './requestClient'
import type { SecureTokenStore } from './secureTokenStore'
import type { useAuthStore } from '@/stores/auth'

type AuthStore = ReturnType<typeof useAuthStore>

export interface LoginRequest { email: string; password: string }

/** Session orchestration; credentials and refresh tokens never enter persistent UI state. */
export class SessionService {
  constructor(
    private readonly client: RequestClient,
    private readonly tokenStore: SecureTokenStore,
    private readonly auth: AuthStore,
    private readonly onAuthenticationRequired: () => void,
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
    } catch {
      await this.tokenStore.remove().catch(() => undefined)
      this.auth.clear()
      return false
    }
  }

  async logout(): Promise<void> {
    try {
      await this.client.request<void>({ method: 'POST', path: '/auth/logout', retryOnUnauthorized: false })
    } finally {
      await this.tokenStore.remove().catch(() => undefined)
      this.auth.clear()
      this.onAuthenticationRequired()
    }
  }
}
