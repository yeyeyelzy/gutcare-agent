import { RequestClient } from './requestClient'
import { nativeSecureTokenStore } from './secureStoreNative'
import type { SecureTokenStore } from './secureTokenStore'
import { SessionService } from './session'
import { UniRequestTransport } from './uniTransport'
import { resolveApiBaseUrl } from '@/config/apiBaseUrl'
import { useAuthStore } from '@/stores/auth'
import type { Pinia } from 'pinia'
import { AuthApi } from './authApi'
import { ProfileApi } from './profileApi'
import { AppRouter, installGlobalRouteGuards } from '../navigation/router'
import { StartupCoordinator } from '../navigation/startup'
import { useRegistrationDraftStore } from '../stores/registrationDraft'
import { RegistrationService } from './registrationService'
import { EmailVerificationService } from './emailVerificationService'
import { PasswordResetService } from './passwordResetService'
import { RecordsApi } from './recordsApi'
import { MoodApi } from './moodApi'
import { ConsentApi } from './consentApi'
import { ActivityApi } from './activityApi'
import { MedicationApi } from './medicationApi'

const apiBaseUrl = resolveApiBaseUrl(import.meta.env.VITE_API_BASE_URL, { allowLocalHttp: import.meta.env.DEV })

/** Build the single app-wide transport after Pinia is installed. */
export function createAppRequestClient(pinia: Pinia): RequestClient {
  const auth = useAuthStore(pinia)
  const router = createAppRouter(auth, pinia)
  return createRequestClient(pinia, nativeSecureTokenStore, () => router.onAuthenticationRequired())
}

function createRequestClient(pinia: Pinia, tokenStore: SecureTokenStore, onAuthenticationRequired: () => void): RequestClient {
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
    onAuthenticationRequired,
    onSecureTokenDeletionFailure: (error) => auth.setLogoutWarning({ kind: 'secure_storage_cleanup_failed', code: error.code }),
  })
  return requestClient
}

export function createAppServices(pinia: Pinia) {
  const auth = useAuthStore(pinia)
  const tokenStore = nativeSecureTokenStore
  const router = createAppRouter(auth, pinia)
  installGlobalRouteGuards(router)
  const requestClient = createRequestClient(pinia, tokenStore, () => router.onAuthenticationRequired())
  const session = new SessionService(requestClient, tokenStore, auth, () => router.onAuthenticationRequired(), () => router.onLogoutCompleted())
  const profileApi = new ProfileApi(requestClient)
  const recordsApi = new RecordsApi(requestClient)
  const moodApi = new MoodApi(requestClient)
  const consentApi = new ConsentApi(requestClient)
  const activityApi = new ActivityApi(requestClient)
  const medicationApi = new MedicationApi(requestClient)
  const authApi = new AuthApi(requestClient, session)
  const registration = new RegistrationService(authApi, useRegistrationDraftStore(pinia))
  const emailVerification = new EmailVerificationService(authApi, useRegistrationDraftStore(pinia))
  const passwordReset = new PasswordResetService(authApi, useRegistrationDraftStore(pinia))
  return {
    requestClient,
    session,
    authApi,
    profileApi,
    recordsApi,
    moodApi,
    consentApi,
    activityApi,
    medicationApi,
    registration,
    emailVerification,
    passwordReset,
    router,
    startup: new StartupCoordinator(session, profileApi, requestClient, auth, router),
  }
}

function createAppRouter(auth: ReturnType<typeof useAuthStore>, pinia: Pinia): AppRouter {
  const registrationDraft = useRegistrationDraftStore(pinia)
  return new AppRouter({
    navigateTo: (url) => { uni.navigateTo({ url }) },
    redirectTo: (url) => { uni.redirectTo({ url }) },
    reLaunch: (url) => { uni.reLaunch({ url }) },
    navigateBack: () => { uni.navigateBack({ delta: 1 }) },
  }, () => auth.state, undefined, () => registrationDraft.cancelWorkflow())
}
