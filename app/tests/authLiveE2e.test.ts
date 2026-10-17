import { describe, expect, it } from 'vitest'
import { AuthApi } from '../src/api/authApi'
import { ProfileApi } from '../src/api/profileApi'
import { RequestClient } from '../src/api/requestClient'
import type { HttpTransport, RequestOptions } from '../src/api/requestClient'
import { MemorySecureTokenStore } from '../src/api/secureTokenStore'
import { SessionService } from '../src/api/session'
import type { useAuthStore } from '../src/stores/auth'

const liveBaseUrl = process.env.GUTCARE_LIVE_E2E_BASE_URL
const liveEmail = process.env.GUTCARE_LIVE_E2E_EMAIL
const livePassword = process.env.GUTCARE_LIVE_E2E_PASSWORD
const expectedProfileId = process.env.GUTCARE_LIVE_E2E_PROFILE_ID
const enabled = Boolean(liveBaseUrl && liveEmail && livePassword && expectedProfileId)

describe.skipIf(!enabled)('APP auth/profile adapters against the live backend', () => {
  it('logs in, reads the token-scoped profile, rotates via SessionService, and logs out', async () => {
    if (!liveBaseUrl || !liveEmail || !livePassword || !expectedProfileId) throw new Error('Live E2E configuration is incomplete.')

    const tokenStore = new MemorySecureTokenStore()
    const liveAuth = {
      accessToken: null as string | null,
      clear() { this.accessToken = null },
      acceptAccessToken(token: string) { this.accessToken = token },
      setLogoutWarning() {},
    }
    const auth = liveAuth as unknown as ReturnType<typeof useAuthStore>

    const transport: HttpTransport = {
      async send<T>(url: string, options: RequestOptions & { headers: Record<string, string> }) {
        const path = new URL(url).pathname
        const response = await fetch(new URL(path, liveBaseUrl), {
          method: options.method,
          headers: options.headers,
          ...(options.data === undefined ? {} : { body: JSON.stringify(options.data) }),
        })
        const text = await response.text()
        let data: unknown
        if (text) {
          try { data = JSON.parse(text) as unknown } catch { data = undefined }
        }
        return { status: response.status, data: data as T }
      },
    }

    const client = new RequestClient({
      baseUrl: 'https://live-contract.invalid/api/v1',
      appVersion: 'b01-4-auth-e2e',
      transport,
      tokenStore,
      getAccessToken: () => liveAuth.accessToken,
      setTokens: (tokens) => liveAuth.acceptAccessToken(tokens.access_token),
      clearSession: async () => liveAuth.clear(),
      onAuthenticationRequired: () => {},
    })
    const session = new SessionService(client, tokenStore, auth, () => {})
    const authApi = new AuthApi(client, session)
    const profileApi = new ProfileApi(client)

    await authApi.login({ email: liveEmail, password: livePassword })
    const initialProfile = await profileApi.getMyProfile()
    expect(initialProfile.id).toBe(expectedProfileId)

    const accessBeforeRefresh = liveAuth.accessToken
    liveAuth.accessToken = 'expired-access-token-for-e2e-only'
    const profileAfterRefresh = await profileApi.getMyProfile()
    expect(profileAfterRefresh.id).toBe(expectedProfileId)
    expect(liveAuth.accessToken).not.toBe('expired-access-token-for-e2e-only')
    expect(liveAuth.accessToken).not.toBe(accessBeforeRefresh)
    expect(await tokenStore.has()).toBe(true)

    await authApi.logout()
    expect(await tokenStore.has()).toBe(false)
    expect(liveAuth.accessToken).toBeNull()
  }, 30_000)
})
