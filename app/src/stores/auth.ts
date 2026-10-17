import { defineStore } from 'pinia'
import type { PatientProfile } from '../api/openapiTypes'
import type { SecureTokenStoreErrorCode } from '../api/secureTokenStore'

export type LogoutWarning =
  | { kind: 'secure_storage_cleanup_failed'; code: SecureTokenStoreErrorCode }
  | { kind: 'server_logout_unconfirmed'; status?: number; requestId?: string }

export type AuthState = 'anonymous' | 'restoring' | 'session_ready' | 'loading_profile' | 'authenticated'
export interface StartupErrorProjection { kind: string; status?: number; code?: string; requestId?: string }

export const useAuthStore = defineStore('auth', {
  state: () => ({
    state: 'anonymous' as AuthState,
    accessToken: null as string | null,
    profile: null as PatientProfile | null,
    profileErrorRequestId: null as string | null,
    startupError: null as StartupErrorProjection | null,
    logoutWarning: null as LogoutWarning | null,
  }),
  actions: {
    beginRestore() { this.state = 'restoring'; this.accessToken = null; this.profile = null; this.profileErrorRequestId = null; this.startupError = null },
    acceptAccessToken(token: string) {
      this.accessToken = token
      this.state = this.profile ? 'authenticated' : 'session_ready'
      this.logoutWarning = null
    },
    beginProfileLoad() { this.state = 'loading_profile' },
    acceptProfile(profile: PatientProfile) {
      this.profile = profile
      this.profileErrorRequestId = null
      this.state = this.accessToken ? 'authenticated' : 'anonymous'
    },
    failProfileLoad(requestId: string | null) {
      this.profile = null
      this.profileErrorRequestId = requestId
      this.state = 'anonymous'
    },
    setStartupError(error: StartupErrorProjection | null) { this.startupError = error },
    setLogoutWarning(warning: LogoutWarning | null) { this.logoutWarning = warning },
    profileLoadFailed() {
      this.profile = null
      this.state = this.accessToken ? 'session_ready' : 'anonymous'
    },
    clear() {
      this.accessToken = null
      this.profile = null
      this.profileErrorRequestId = null
      this.startupError = null
      this.logoutWarning = null
      this.state = 'anonymous'
    },
  },
})
