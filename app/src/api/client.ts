import { RequestClient } from './requestClient'
import { nativeSecureTokenStore } from './secureStoreNative'
import type { SecureTokenStore } from './secureTokenStore'
import { SessionService } from './session'
import { UniRequestTransport } from './uniTransport'
import { resolveApiBaseUrl } from '@/config/apiBaseUrl'
import { useAuthStore } from '@/stores/auth'
import type { Pinia } from 'pinia'

const apiBaseUrl = resolveApiBaseUrl(import.meta.env.VITE_API_BASE_URL, { allowLocalHttp: import.meta.env.DEV })

/** Build the single app-wide transport after Pinia is installed. */
export function createAppRequestClient(pinia: Pinia): RequestClient {
  return createRequestClient(pinia, nativeSecureTokenStore)
}

function createRequestClient(pinia: Pinia, tokenStore: SecureTokenStore): RequestClient {
  const auth = useAuthStore(pinia)
  const requestClient = new RequestClient({
    baseUrl: apiBaseUrl,
    appVersion: import.meta.env.VITE_APP_VERSION || '0.1.0',
    transport: new UniRequestTransport(),
    // Native-only adapter; unsupported targets fail closed without web storage fallback.
    tokenStore,
    getAccessToken: () => auth.accessToken,
    setTokens: (tokens) => auth.acceptAccessToken(tokens.access_token),
    clearSession: async () => {
      auth.clear()
    },
    onAuthenticationRequired: () => {
      uni.reLaunch({ url: '/pages/auth/login' })
    },
  })
  return requestClient
}

export function createAppServices(pinia: Pinia) {
  const auth = useAuthStore(pinia)
  const tokenStore = nativeSecureTokenStore
  const requestClient = createRequestClient(pinia, tokenStore)
  return {
    requestClient,
    session: new SessionService(requestClient, tokenStore, auth, () => uni.reLaunch({ url: '/pages/auth/login' })),
  }
}
