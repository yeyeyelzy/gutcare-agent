import { defineStore } from 'pinia'
import type { PatientProfile } from '../api/openapiTypes'

export type AuthState = 'anonymous' | 'restoring' | 'session_ready' | 'loading_profile' | 'authenticated'

export const useAuthStore = defineStore('auth', {
  state: () => ({
    state: 'anonymous' as AuthState,
    accessToken: null as string | null,
    profile: null as PatientProfile | null,
    profileErrorRequestId: null as string | null,
  }),
  actions: {
    beginRestore() { this.state = 'restoring'; this.accessToken = null; this.profile = null; this.profileErrorRequestId = null },
    acceptAccessToken(token: string) {
      this.accessToken = token
      this.state = this.profile ? 'authenticated' : 'session_ready'
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
    profileLoadFailed() {
      this.profile = null
      this.state = this.accessToken ? 'session_ready' : 'anonymous'
    },
    clear() {
      this.accessToken = null
      this.profile = null
      this.profileErrorRequestId = null
      this.state = 'anonymous'
    },
  },
})
